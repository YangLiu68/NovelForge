"""Command-line entry point: `novelforge <command>`."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def cmd_migrate(args: argparse.Namespace) -> int:
    from alembic import command

    if args.revision == "base":
        command.downgrade(_alembic_config(), "base")
    else:
        command.upgrade(_alembic_config(), args.revision)
    return 0


def cmd_import_sample(args: argparse.Namespace) -> int:
    from novelforge.config import get_settings
    from novelforge.db import get_sessionmaker
    from novelforge.services.importer import import_sample

    with get_sessionmaker()() as session:
        result = import_sample(session, get_settings().samples_dir, args.name)
        session.commit()
        state = "imported" if result.created else "already present"
        print(f"{args.name}: {state} (novel id {result.novel.id})")
    return 0


def cmd_eval_sample(args: argparse.Namespace) -> int:
    """Score the contradiction report against the sample's labelled ground truth.

    Default: pure in-memory run (no database). --db: import into the database and score the
    report the API would return.
    """
    from novelforge.config import get_settings
    from novelforge.core.contradictions import detect_contradictions
    from novelforge.core.domain import ChapterRef, CharacterRef
    from novelforge.core.evaluation import evaluate
    from novelforge.core.extraction import EXTRACTOR, extract_claims
    from novelforge.core.sample import load_sample

    settings = get_settings()
    sample = load_sample(settings.samples_dir, args.name)
    bodies = {c.number: c.body for c in sample.chapters}
    if args.db:
        from novelforge.db import get_sessionmaker
        from novelforge.services.importer import import_sample
        from novelforge.services.report import contradiction_report

        with get_sessionmaker()() as session:
            result = import_sample(session, settings.samples_dir, args.name)
            session.commit()
            findings, _ = contradiction_report(
                session, result.novel.id, settings.report_min_confidence
            )
            # Score against the stored text, which is what the cited offsets index into.
            bodies = {c.number: c.body for c in result.novel.chapters}
    else:
        characters = [
            CharacterRef(str(c.id), c.name, tuple(c.aliases), c.attributes)
            for c in sample.characters
        ]
        chapters = [
            ChapterRef(str(c.id), c.number, c.title, c.body, 1, c.story_day)
            for c in sample.chapters
        ]
        claims = [cl for ch in chapters for cl in extract_claims(ch, characters)]
        findings = detect_contradictions(
            claims, chapters, characters, min_confidence=settings.report_min_confidence
        )
    result = evaluate(findings, sample.ground_truth, bodies).as_dict()
    result.update(
        {
            "sample": args.name,
            "extractor": EXTRACTOR,
            "mode": "db" if args.db else "in-memory",
            "min_confidence": settings.report_min_confidence,
        }
    )
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(
        f"sample={args.name} extractor={EXTRACTOR} mode={result['mode']} "
        f"min_confidence={result['min_confidence']}"
    )
    print(
        f"findings={result['findings']} TP={result['true_positives']} "
        f"FP={result['false_positives']} FN={result['false_negatives']}"
    )
    print(
        f"precision={result['precision']} recall(all)={result['recall_all']} "
        f"recall(m1-detectable)={result['recall_detectable']}"
    )
    print(f"negatives violated={result['negatives_violated']}/{result['negatives']}")
    print(
        f"citation precision={result['citation_precision']} "
        f"({result['cited_spans_correct']}/{result['cited_spans']} cited spans) "
        f"citation recall={result['citation_recall']} "
        f"({result['labelled_spans_covered']}/{result['labelled_spans_total']} labelled spans)"
    )
    for m in result["missed"]:
        print(f"missed {m['id']}: {m['reason']}")
    return 0


def cmd_gen_corpus(args: argparse.Namespace) -> int:
    from novelforge.bench.generate import generate

    gt = generate(Path(args.out), args.chapters, args.seed, args.filler)
    counts = {k: len(v) for k, v in gt.items() if isinstance(v, list)}
    print(f"wrote {args.out}: {args.chapters} chapters, seed {args.seed}, {counts}")
    return 0


def cmd_import_corpus(args: argparse.Namespace) -> int:
    from novelforge.db import get_sessionmaker
    from novelforge.services.importer import import_folder

    with get_sessionmaker()() as session:
        result = import_folder(session, Path(args.path))
        session.commit()
        state = "imported" if result.created else "already present"
        print(f"{args.path}: {state} (novel id {result.novel.id})")
    return 0


def cmd_import_text(args: argparse.Namespace) -> int:
    from novelforge.core.plaintext import DEFAULT_HEADING, split_chapters, strip_gutenberg
    from novelforge.core.sample import text_novel
    from novelforge.db import get_sessionmaker
    from novelforge.services.importer import import_novel

    cast: list[dict] = []
    if args.book:
        from novelforge.bench import real_text

        root = BACKEND_DIR.parent / "bench"
        book = real_text.load_manifest(root / "real" / "books.yaml")[args.book]
        raw, _ = real_text.fetch(book, root / "corpora" / "real")
        chapters = [(c.title, c.body) for c in real_text.book_chapters(book, raw)]
        title, slug = book["title"], args.book
        cast = [
            {**c, "pronouns": real_text.PRONOUNS_BY_GENDER.get(c.get("gender", ""))}
            for c in book["characters"]
        ]
    else:
        if not args.file or not args.title:
            print("give a FILE and --title, or --book ID", file=sys.stderr)
            return 2
        raw = Path(args.file).read_text(encoding="utf-8-sig")
        heading = args.heading or DEFAULT_HEADING
        parts = split_chapters(strip_gutenberg(raw), heading, args.title_lines)
        if not parts:
            print("no chapter headings found (see --heading)", file=sys.stderr)
            return 1
        chapters = [(c.title, c.body) for c in parts]
        title = args.title
        slug = args.slug or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    novel = text_novel(slug, title, chapters, cast)
    with get_sessionmaker()() as session:
        result = import_novel(session, novel)
        session.commit()
    state = "imported" if result.created else "already present"
    words = sum(len(b.split()) for _, b in chapters)
    print(f"{title}: {state}, {len(chapters)} chapters, {words:,} words")
    print(f"novel id {result.novel.id}")
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    import logging
    import signal
    import threading

    from novelforge.db import get_sessionmaker
    from novelforge.jobs import Worker, load_handlers, run_pending

    logging.basicConfig(level="INFO", format="%(message)s")
    load_handlers()
    if args.once:
        print(f"ran {run_pending(get_sessionmaker())} jobs")
        return 0
    worker = Worker(get_sessionmaker())
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    worker.start()
    stop.wait()
    worker.stop()
    return 0


def cmd_bench_retrieval(args: argparse.Namespace) -> int:
    from sqlalchemy.engine import make_url

    from novelforge.bench import retrieval_eval
    from novelforge.db import resolve_database_url

    report = retrieval_eval.run(
        Path(args.corpus),
        make_url(resolve_database_url()),
        args.embedder,
        args.reranker,
        args.modes.split(","),
        max_queries=args.max_queries,
    )
    path = retrieval_eval.save(report, Path(args.out))
    print(retrieval_eval.to_markdown(report))
    print(f"\nsaved {path} and {path.with_suffix('.md')}")
    return 0


def cmd_bench_extraction(args: argparse.Namespace) -> int:
    from novelforge.bench import extraction_eval

    out = Path(args.out)
    cache = None
    if args.extractor != "rules":
        safe_llm = args.extractor.replace("/", "_").replace(":", "-")
        cache = (
            Path(args.cache)
            if args.cache
            else (out / "llm-cache" / f"{Path(args.corpus).name}-{safe_llm}.jsonl")
        )
    report = extraction_eval.run(
        Path(args.corpus),
        args.extractor,
        args.max_chapters,
        cache,
        check_values=not args.no_value_check,
        sheet_pronouns=not args.no_sheet_pronouns,
    )
    out.mkdir(parents=True, exist_ok=True)
    safe = report["extractor"].replace("/", "_").replace(":", "-")
    suffix = "" if report["value_check"] else "-no-value-check"
    suffix += "" if report["sheet_pronouns"] else "-inferred-pronouns"
    path = out / f"extraction-{report['corpus']}-{safe}-{report['chapters']}ch{suffix}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    path.with_suffix(".md").write_text(extraction_eval.to_markdown(report) + "\n", encoding="utf-8")
    print(extraction_eval.to_markdown(report))
    print(f"\nsaved {path}")
    return 0


def cmd_bench_consistency(args: argparse.Namespace) -> int:
    from sqlalchemy.engine import make_url

    from novelforge.bench import consistency_eval
    from novelforge.db import resolve_database_url

    report = consistency_eval.run(
        Path(args.corpus),
        make_url(resolve_database_url()),
        extractor=args.extractor,
        embedder_spec=args.embedder,
        k=args.k,
        max_chapters=args.max_chapters,
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    safe = (report["extraction"]["extractor"] + "-" + report["embedder"]).replace("/", "_")
    path = (
        out / f"consistency-{report['corpus']}-{safe.replace(':', '-')}-{report['chapters']}ch.json"
    )
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    path.with_suffix(".md").write_text(
        consistency_eval.to_markdown(report) + "\n", encoding="utf-8"
    )
    print(consistency_eval.to_markdown(report))
    print(f"\nsaved {path}")
    return 0


def cmd_bench_real(args: argparse.Namespace) -> int:
    from novelforge.bench import real_text

    root = BACKEND_DIR.parent / "bench"
    report, todo = real_text.run(
        args.book,
        Path(args.manifest) if args.manifest else root / "real" / "books.yaml",
        root / "corpora" / "real",
        root / "real" / "labels",
        sheet_pronouns=not args.no_sheet_pronouns,
        claims_file=Path(args.claims) if args.claims else None,
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    suffix = "" if report["sheet_pronouns"] else "-inferred-pronouns"
    path = out / f"real-{report['book']}-{report['extractor']}{suffix}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    path.with_suffix(".md").write_text(real_text.to_markdown(report) + "\n", encoding="utf-8")
    print(real_text.to_markdown(report))
    print(f"\nsaved {path}")
    if todo:
        default = out / f"real-{report['book']}-unlabelled.jsonl"
        todo_path = Path(args.todo) if args.todo else default
        todo_path.write_text(
            "".join(json.dumps(t, ensure_ascii=False) + "\n" for t in todo), encoding="utf-8"
        )
        print(f"{len(todo)} unlabelled items written to {todo_path}")
    return 0


def cmd_audit_story(args: argparse.Namespace) -> int:
    from novelforge.bench import story_eval
    from novelforge.config import get_settings
    from novelforge.llm.cache import CachingLLM
    from novelforge.llm.registry import get_llm

    settings = get_settings()
    folder = Path(args.sample)
    if not folder.exists():
        folder = settings.samples_dir / args.sample
    out = Path(args.out)
    safe_llm = args.llm.replace(":", "-").replace("/", "-")
    cache = (
        Path(args.cache)
        if args.cache
        else (out / "llm-cache" / f"story-{folder.name}-{safe_llm}.jsonl")
    )
    if args.replay:
        # Re-score a recorded run with the current checks: no model is loaded or called.
        from novelforge.llm.cache import ReplayLLM

        llm = ReplayLLM(args.llm, cache.parent)
    else:
        llm = CachingLLM(get_llm(args.llm), cache)
    from novelforge.llm.base import LLMError

    try:
        report = story_eval.run(
            folder, llm, progress=lambda msg: print(f"  {msg}", file=sys.stderr, flush=True)
        )
    except LLMError as exc:
        print(f"audit stopped: {exc}", file=sys.stderr)
        return 1
    report["replayed"] = bool(args.replay)
    report["cache"] = {
        "path": str(cache),
        "hits": getattr(llm, "hits", None),
        "misses": getattr(llm, "misses", None),
    }
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"story-{folder.name}-{safe_llm}-{report['audit']['prompt_version']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    path.with_suffix(".md").write_text(story_eval.to_markdown(report) + "\n", encoding="utf-8")
    print(story_eval.to_markdown(report))
    how = (
        "replayed from the recording"
        if args.replay
        else f"cache {llm.hits} hits, {llm.misses} misses"
    )
    print(f"\nsaved {path} ({how})")
    return 0


def cmd_bench_load(args: argparse.Namespace) -> int:
    from sqlalchemy.engine import make_url

    from novelforge.bench import load_test
    from novelforge.db import resolve_database_url

    report = load_test.run(
        Path(args.corpus), make_url(resolve_database_url()), args.embedder, args.queries
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"load-{report['corpus']}-{report['embedder'].replace(':', '-')}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    path.with_suffix(".md").write_text(load_test.to_markdown(report) + "\n", encoding="utf-8")
    print(load_test.to_markdown(report))
    print(f"\nsaved {path}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("novelforge.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_local_db(args: argparse.Namespace) -> int:
    from novelforge.config import get_settings
    from novelforge.localdb import local_server_url, stop_local_server

    settings = get_settings()
    if args.stop:
        stopped = stop_local_server(settings.local_pgdata)
        print("local PostgreSQL stopped" if stopped else "local PostgreSQL was not running")
    else:
        print(local_server_url(settings.local_pgdata, args.database))
    return 0


def cmd_e2e_server(args: argparse.Namespace) -> int:
    """Recreate an empty database, migrate it and serve the API (used by Playwright)."""
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    from novelforge.config import get_settings
    from novelforge.db import resolve_database_url

    base = make_url(resolve_database_url())
    target = base.set(database=args.database)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{args.database}" WITH (FORCE)')
        conn.exec_driver_sql(f'CREATE DATABASE "{args.database}"')
    admin.dispose()
    os.environ["DATABASE_URL"] = target.render_as_string(hide_password=False)
    get_settings.cache_clear()
    cmd_migrate(argparse.Namespace(revision="head"))
    return cmd_serve(argparse.Namespace(host=args.host, port=args.port, reload=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="novelforge")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("migrate", help="apply Alembic migrations (default: head)")
    p.add_argument("revision", nargs="?", default="head", help="'head', a revision, or 'base'")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("import-sample", help="import a sample novel (idempotent)")
    p.add_argument("name", nargs="?", default="lanternfall")
    p.set_defaults(func=cmd_import_sample)

    p = sub.add_parser("eval-sample", help="score the contradiction report on a sample")
    p.add_argument("name", nargs="?", default="lanternfall")
    p.add_argument("--db", action="store_true", help="run through the database")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_eval_sample)

    p = sub.add_parser("gen-corpus", help="generate a synthetic benchmark corpus")
    p.add_argument("--chapters", type=int, default=100)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--filler", type=int, default=0, help="extra scene paragraphs per chapter")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_gen_corpus)

    p = sub.add_parser("import-corpus", help="import a corpus folder (idempotent)")
    p.add_argument("path")
    p.set_defaults(func=cmd_import_corpus)

    p = sub.add_parser("import-text", help="import a plain-text novel (or a bench/real book)")
    p.add_argument("file", nargs="?", help="a .txt file with CHAPTER headings")
    p.add_argument("--title", default=None)
    p.add_argument("--slug", default=None)
    p.add_argument("--heading", default=None, help="chapter heading regex (default: CHAPTER ...)")
    p.add_argument("--title-lines", type=int, default=0, help="title lines after each heading")
    p.add_argument("--book", default=None, help="a book id from bench/real/books.yaml instead")
    p.set_defaults(func=cmd_import_text)

    p = sub.add_parser("worker", help="run the background job worker")
    p.add_argument("--once", action="store_true", help="drain the queue and exit")
    p.set_defaults(func=cmd_worker)

    p = sub.add_parser("bench-retrieval", help="retrieval benchmark on a generated corpus")
    p.add_argument("corpus")
    p.add_argument("--embedder", default="hash")
    p.add_argument("--reranker", default="lexical")
    p.add_argument("--modes", default="keyword,fts,vector,hybrid,hybrid_rerank")
    p.add_argument("--max-queries", type=int, default=None)
    p.add_argument("--out", default=str(BACKEND_DIR.parent / "bench" / "results"))
    p.set_defaults(func=cmd_bench_retrieval)

    p = sub.add_parser("bench-extraction", help="extraction benchmark on a generated corpus")
    p.add_argument("corpus")
    p.add_argument("--extractor", default="rules", help="rules | mock | ollama:<model> | anthropic")
    p.add_argument("--max-chapters", type=int, default=None)
    p.add_argument(
        "--cache",
        default=None,
        help="LLM response cache (JSONL); default bench/results/llm-cache/<corpus>-<llm>",
    )
    p.add_argument(
        "--no-value-check",
        action="store_true",
        help="ablation: keep LLM facts whose value is not in their quote",
    )
    p.add_argument(
        "--no-sheet-pronouns",
        action="store_true",
        help="ablation: drop pronouns from the character sheets (inferred per chapter)",
    )
    p.add_argument("--out", default=str(BACKEND_DIR.parent / "bench" / "results"))
    p.set_defaults(func=cmd_bench_extraction)

    p = sub.add_parser("bench-consistency", help="contradiction benchmark with memory ablation")
    p.add_argument("corpus")
    p.add_argument("--extractor", default="rules", help="rules | mock | ollama:<model> | anthropic")
    p.add_argument("--embedder", default="hash")
    p.add_argument("--k", type=int, default=5, help="passages retrieved per claim")
    p.add_argument("--max-chapters", type=int, default=None)
    p.add_argument("--out", default=str(BACKEND_DIR.parent / "bench" / "results"))
    p.set_defaults(func=cmd_bench_consistency)

    p = sub.add_parser("bench-real", help="precision on a public-domain novel (hand labels)")
    p.add_argument("book", help="book id from bench/real/books.yaml")
    p.add_argument("--manifest", default=None)
    p.add_argument("--todo", default=None, help="where to write unlabelled items (JSONL)")
    p.add_argument(
        "--no-sheet-pronouns",
        action="store_true",
        help="ablation: leave pronouns off the character sheets (inferred per chapter)",
    )
    p.add_argument(
        "--claims", default=None, help="score claims from this JSONL instead of extracting"
    )
    p.add_argument("--out", default=str(BACKEND_DIR.parent / "bench" / "results"))
    p.set_defaults(func=cmd_bench_real)

    p = sub.add_parser(
        "audit-story", help="story-logic audit (motives, plot, pacing) on a sample folder"
    )
    p.add_argument("sample", nargs="?", default="xueye-dangpu", help="sample name or folder")
    p.add_argument("--llm", default="ollama:qwen2.5:7b", help="ollama:<model> | anthropic[:model]")
    p.add_argument("--cache", default=None, help="LLM record-and-replay cache (JSONL)")
    p.add_argument(
        "--replay", action="store_true", help="answer only from recordings of --llm (no model)"
    )
    p.add_argument("--out", default=str(BACKEND_DIR.parent / "bench" / "results"))
    p.set_defaults(func=cmd_audit_story)

    p = sub.add_parser("bench-load", help="load test on a generated corpus")
    p.add_argument("corpus")
    p.add_argument("--embedder", default="hash")
    p.add_argument("--queries", type=int, default=50)
    p.add_argument("--out", default=str(BACKEND_DIR.parent / "bench" / "results"))
    p.set_defaults(func=cmd_bench_load)

    p = sub.add_parser("serve", help="run the API server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("local-db", help="start the local pgserver PostgreSQL and print its URL")
    p.add_argument("--database", default="novelforge")
    p.add_argument("--stop", action="store_true")
    p.set_defaults(func=cmd_local_db)

    p = sub.add_parser("e2e-server", help="fresh database + API server for end-to-end tests")
    p.add_argument("--database", default="novelforge_e2e")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_e2e_server)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    finally:
        from novelforge.retrieval.embedders import release_models

        release_models()


if __name__ == "__main__":
    sys.exit(main())
