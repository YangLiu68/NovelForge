"""Run the story-logic audit on a sample folder and score it against narrative_truth.yaml.

    novelforge audit-story xueye-dangpu --llm ollama:qwen2.5:7b

LLM calls go through the record-and-replay cache (bench/results/llm-cache/...), so a finished run
can be re-scored offline and a reader can replay it without the model.
"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Any

import yaml

from novelforge.core.domain import ChapterRef
from novelforge.core.sample import SampleNovel, load_folder
from novelforge.llm.base import LLM
from novelforge.narrative.audit import CastMember, StoryAudit, audit_story
from novelforge.narrative.score import score

VERDICT_ZH = {
    "consistent": "合理",
    "unmotivated": "动机缺失",
    "contradicts": "与人设冲突",
    "malice_without_cause": "为坏而坏",
    "delayed": "后文有解释",
    "unverified": "依据不足",
    "knowledge_leak": "信息来源不明",
    "deus_ex_machina": "天降解围",
    "dangling_setup": "伏笔未回收",
    "causality": "因果不通",
    "flat_stretch": "节奏平",
    "no_hook": "章末无钩子",
}


def sample_inputs(novel: SampleNovel) -> tuple[list[ChapterRef], list[CastMember]]:
    chapters = [
        ChapterRef(str(c.id), c.number, c.title, c.body, 1, c.story_day) for c in novel.chapters
    ]
    cast = [CastMember(c.name, tuple(c.aliases), c.description) for c in novel.characters]
    return chapters, cast


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() or None
    except OSError:
        return None


def run(folder: Path, llm: LLM, progress=None) -> dict[str, Any]:
    novel = load_folder(folder)
    chapters, cast = sample_inputs(novel)
    audit = audit_story(chapters, cast, llm, progress=progress)
    truth_path = folder / "narrative_truth.yaml"
    truth = yaml.safe_load(truth_path.read_text(encoding="utf-8")) if truth_path.exists() else {}
    report: dict[str, Any] = {
        "sample": novel.slug,
        "title": novel.title,
        "audit": audit.to_dict(),
        "score": score(audit, truth, chapters) if truth else None,
        "grounding": grounding(audit),
        "environment": {
            "machine": platform.machine(),
            "python": platform.python_version(),
            "commit": _git_commit(),
        },
    }
    return report


def grounding(audit: StoryAudit) -> dict[str, Any]:
    """How much of the model's output survived the deterministic checks."""
    rejected: dict[str, int] = {}
    for r in audit.rejected:
        key = f"{r['stage']}: {r['reason']}"
        rejected[key] = rejected.get(key, 0) + 1
    located: dict[str, int] = {}
    for x in [*audit.notes, *audit.beats]:
        method = getattr(x, "located", None)
        if method:
            located[method] = located.get(method, 0) + 1
    downgraded: dict[str, int] = {}
    for j in audit.judgements:
        if j.verdict != j.model_verdict:
            key = f"{j.model_verdict} -> {j.verdict}"
            downgraded[key] = downgraded.get(key, 0) + 1
    return {
        "notes_kept": sum(1 for n in audit.notes if n.chapter is not None),
        "beats_kept": len(audit.beats),
        "setups_kept": len(audit.setups),
        "judgements": len(audit.judgements),
        "rejected": rejected,
        "quotes_located_by": located,
        "verdicts_changed_by_checks": downgraded,
        "errors": audit.errors,
    }


def to_markdown(report: dict[str, Any]) -> str:
    a = report["audit"]
    lines = [
        f"*{report['title']}* (`{report['sample']}`): {len(a['chapters'])} chapters, "
        f"{len(a['cast'])} characters. LLM `{a['llm']}`, prompts `{a['prompt_version']}`"
        f"{', checks `' + a['checks_version'] + '`' if a.get('checks_version') else ''}, "
        f"{a['usage'].get('calls', 0)} calls, {a['usage'].get('input_tokens', 0):,} input / "
        f"{a['usage'].get('output_tokens', 0):,} output tokens, "
        f"{a['usage'].get('llm_seconds', 0)} s in the model.",
        "",
    ]
    s = report.get("score")
    if s:
        lines += [
            f"Labelled problems found: **{s['problems_found']} / {s['problems']}** "
            f"({s.get('located', s['problems_found'])} flagged at the right place with any "
            "diagnosis); "
            f"traps set off: **{s['traps_set_off']} / {s['traps']}**; "
            f"issues reported: {s['issues_reported']} "
            f"({len(s['unlabelled_issues'])} not on a label).",
            "",
            "| Label | Kind | Result | Issues |",
            "|---|---|---|---|",
        ]
        for p in s["problem_rows"]:
            res = "found" if p["found"] else "missed"
            if not p["found"] and p.get("located_other_kind"):
                res = f"other diagnosis ({', '.join(p['located_other_kind'])})"
            lines.append(f"| {p['id']} | {p['kind']} | {res} | {', '.join(p['issues'])} |")
        for t in s["trap_rows"]:
            res = "set off" if t["set_off"] else "clean"
            extra = f" (verdicts: {', '.join(t['verdicts'])})" if t["verdicts"] else ""
            lines.append(f"| {t['id']} | trap | {res}{extra} | {', '.join(t['issues'])} |")
        lines.append("")
    lines += [
        "| Issue | Severity | Kind | Chapter | Character | What |",
        "|---|---|---|---|---|---|",
    ]
    for i in a["issues"]:
        kind = VERDICT_ZH.get(i["kind"], i["kind"]) if a["language"] == "zh" else i["kind"]
        what = i["title"].replace("|", "/")
        lines.append(
            f"| {i['id']} | {i['severity']} | {kind} | {i['chapter']} | "
            f"{i['character'] or ''} | {what} |"
        )
    g = report["grounding"]
    lines += [
        "",
        f"Grounding: {g['notes_kept']} notes, {g['beats_kept']} beats, {g['setups_kept']} "
        f"setups kept; quotes located by {g['quotes_located_by']}; rejected {g['rejected']}; "
        f"verdicts changed by checks {g['verdicts_changed_by_checks']}; errors {len(g['errors'])}.",
    ]
    return "\n".join(lines)
