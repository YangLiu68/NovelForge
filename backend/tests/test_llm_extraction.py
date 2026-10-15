import json
from types import SimpleNamespace

import httpx
import pytest

from novelforge.core.domain import ChapterRef, CharacterRef
from novelforge.core.extraction import extract_claims
from novelforge.extraction.mock_responder import rules_backed_mock
from novelforge.extraction.runner import extract_with_llm, windows
from novelforge.extraction.schema import SCHEMA
from novelforge.extraction.verify import locate
from novelforge.llm.anthropic_backend import AnthropicLLM
from novelforge.llm.base import LLMError, cost
from novelforge.llm.mock import MockLLM
from novelforge.llm.ollama_backend import OllamaLLM

MARA = CharacterRef("m", "Mara Venn", ("the cartographer",))
TOMAS = CharacterRef("t", "Tomas Hale")
BODY = (
    "Mara's eyes were grey.\n\nTomas was in Hollin that morning. Three days later Tomas was in "
    "Varrow.\n\n“Tomas has blue eyes,” said the clerk."
)
CH = ChapterRef("c1", 4, "Four", BODY, 2, 100)


def fact(**kw):
    base = {
        "subject": "Mara Venn",
        "kind": "eye_color",
        "value": "grey",
        "object": "",
        "quote": "Mara's eyes were grey",
        "modality": "asserted",
        "confidence": 0.9,
        "day_offset": 0,
    }
    return {**base, **kw}


def test_locate_exact_normalised_and_missing():
    assert locate(BODY, "Mara's eyes were grey").method == "exact"
    # Straight quotes and different whitespace still map back to exact offsets.
    found = locate(BODY, '"Tomas  has blue eyes," said')
    assert found and found.method == "normalized"
    assert BODY[found.start : found.end] == "“Tomas has blue eyes,” said"
    assert locate(BODY, "Mara's eyes were green") is None
    assert locate(BODY, "ab") is None


def test_windows_cover_whole_paragraphs():
    body = "\n\n".join(f"Paragraph {i} " + "word " * 50 for i in range(10))
    parts = windows(body, max_words=120)
    assert len(parts) == 5
    assert parts[0][0] == 0 and parts[-1][1] == len(body.rstrip())
    for s, e in parts:
        assert body[s:e].startswith("Paragraph")


def test_runner_validates_resolves_and_verifies():
    llm = MockLLM()
    llm.queue_json(
        {
            "facts": [
                fact(),
                fact(
                    subject="the cartographer",
                    kind="hair_color",
                    value="black",
                    quote="not in the text at all",
                ),
                fact(subject="Nobody Known", quote="Mara's eyes were grey"),
                fact(kind="age", value="eleventy", quote="Mara's eyes were grey"),
                fact(
                    subject="Tomas Hale",
                    kind="location",
                    value="Varrow",
                    quote="Three days later Tomas was in Varrow",
                    day_offset=3,
                ),
                fact(
                    subject="Tomas Hale",
                    kind="eye_color",
                    value="blue",
                    quote='"Tomas has blue eyes," said the clerk',
                    modality="reported",
                    confidence=0.95,
                ),
                fact(
                    subject="world",
                    kind="world_rule",
                    value="Iron cannot be enchanted",
                    quote="Mara's eyes were grey",
                ),
                "not even an object",
            ]
        }
    )
    run = extract_with_llm(CH, [MARA, TOMAS], llm)
    reasons = sorted(r["reason"] for r in run.rejected)
    assert reasons == ["malformed value", "not an object", "quote not found", "unknown subject"]
    by_pred = {c.predicate: c for c in run.claims}
    assert by_pred["eye_color"].subject_id in ("m", "t")
    loc = by_pred["location"]
    assert loc.effective_day == 103 and loc.details["day_offset"] == 3
    assert loc.spans[0].quote == "Three days later Tomas was in Varrow"
    reported = next(c for c in run.claims if c.modality == "reported")
    assert reported.details["quote_match"] == "normalized"
    rule = by_pred["world_rule"]
    assert rule.subject_id == "" and rule.subject_text == "world"
    for c in run.claims:
        s = c.spans[0]
        assert BODY[s.start : s.end] == s.quote
        assert c.extractor == "llm:mock"


def test_runner_records_non_retryable_errors_and_raises_transport():
    class Broken(MockLLM):
        def __init__(self, kind):
            super().__init__()
            self.kind = kind

        def generate_json(self, *a, **k):
            raise LLMError(self.kind, "nope")

    run = extract_with_llm(CH, [MARA], Broken("invalid_json"))
    assert run.claims == [] and "invalid_json" in run.errors[0]
    with pytest.raises(LLMError):
        extract_with_llm(CH, [MARA], Broken("transport"))


def test_rules_backed_mock_matches_rule_extractor():
    run = extract_with_llm(CH, [MARA, TOMAS], rules_backed_mock())
    rules = extract_claims(CH, [MARA, TOMAS])
    as_set = lambda cs: {(c.predicate, c.value, c.modality, c.spans[0].start) for c in cs}  # noqa: E731
    assert as_set(run.claims) == as_set(rules)
    assert run.rejected == [] and run.calls == 1


def test_schema_is_strict():
    item = SCHEMA["properties"]["facts"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])


def test_cost_table():
    assert cost("claude-opus-5-5", 1_000_000, 100_000, local=False) == 6.0
    assert cost("some-unpriced-model", 10, 10, local=False) is None
    assert cost("anything", 10, 10, local=True) == 0.0


def _fake_anthropic(stop_reason="end_turn", text='{"facts": []}'):
    calls = {}

    def create(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(
            stop_reason=stop_reason,
            stop_details=SimpleNamespace(category="cyber"),
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text=text),
            ],
            usage=SimpleNamespace(input_tokens=1200, output_tokens=300),
            model="claude-opus-5-5",
        )

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    return client, calls


def test_anthropic_backend_request_shape_and_usage():
    client, calls = _fake_anthropic()
    llm = AnthropicLLM(client=client)
    result = llm.generate_json("sys", "prompt", SCHEMA)
    assert calls["model"] == "claude-opus-5-5"
    assert calls["fallbacks"] == "default"
    assert calls["betas"] == ["server-side-fallback-2026-07-01"]
    assert calls["output_config"]["format"]["type"] == "json_schema"
    assert "title" not in calls["output_config"]["format"]["schema"]
    assert calls["output_config"]["effort"] == "medium"
    assert "thinking" not in calls  # Opus 5.5 always thinks; effort is the control
    assert result.data == {"facts": []}
    assert result.cost_usd == pytest.approx(1200 / 1e6 * 4 + 300 / 1e6 * 20)


@pytest.mark.parametrize("stop,kind", [("refusal", "refusal"), ("max_tokens", "max_tokens")])
def test_anthropic_backend_stop_reasons(stop, kind):
    client, _ = _fake_anthropic(stop_reason=stop)
    with pytest.raises(LLMError) as exc:
        AnthropicLLM(client=client).generate_json("s", "p", SCHEMA)
    assert exc.value.kind == kind


def test_anthropic_backend_invalid_json():
    client, _ = _fake_anthropic(text="{not json")
    with pytest.raises(LLMError) as exc:
        AnthropicLLM(client=client).generate_json("s", "p", SCHEMA)
    assert exc.value.kind == "invalid_json"


def test_ollama_backend_json_and_stream():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "qwen2.5:7b"
        if body["stream"]:
            lines = [
                {"message": {"content": "Fog "}, "done": False},
                {"message": {"content": "rolled in."}, "done": False},
                {"done": True, "done_reason": "stop", "prompt_eval_count": 40, "eval_count": 4},
            ]
            return httpx.Response(200, text="\n".join(json.dumps(x) for x in lines))
        assert "title" not in body["format"]
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"facts": []}'},
                "done_reason": "stop",
                "prompt_eval_count": 50,
                "eval_count": 5,
            },
        )

    llm = OllamaLLM("qwen2.5:7b", "http://ollama.test", transport=httpx.MockTransport(handler))
    result = llm.generate_json("s", "p", SCHEMA)
    assert result.data == {"facts": []} and result.input_tokens == 50 and result.cost_usd == 0
    chunks = list(llm.stream_text("s", "p"))
    assert "".join(c.text for c in chunks) == "Fog rolled in."
    assert chunks[-1].done and chunks[-1].result.output_tokens == 4


def test_mock_stream_cancel():
    import threading

    llm = MockLLM(chunk_delay=0)
    llm.queue_text("one two three four five six seven eight nine ten")
    cancel = threading.Event()
    seen = []
    for chunk in llm.stream_text("s", "p", cancel=cancel):
        seen.append(chunk)
        if len(seen) == 2:
            cancel.set()
    assert seen[-1].cancelled and seen[-1].done
    assert seen[-1].result.text == "one two three four five six "


def test_value_must_be_grounded_in_the_quote():
    from novelforge.extraction.runner import value_grounded

    assert value_grounded("location", "Hollin", "Tomas was in Hollin")
    assert not value_grounded("location", "the harbour", "Jorin could not swim.")
    assert value_grounded("age", "31", "At thirty-one, Mara")
    assert value_grounded("handedness", "left", "Being left-handed, Tomas")
    assert not value_grounded("eye_color", "green", "eyes the colour of sea glass")
    assert value_grounded("world_rule", "anything", "unrelated")  # free-text kinds pass
    llm = MockLLM()
    llm.queue_json(
        {
            "facts": [
                fact(
                    subject="Tomas Hale",
                    kind="location",
                    value="the harbour",
                    quote="Tomas was in Hollin that morning",
                )
            ]
        }
    )
    run = extract_with_llm(CH, [MARA, TOMAS], llm)
    assert run.claims == [] and run.rejected[0]["reason"] == "value not in quote"


def test_caching_llm_replays_without_calling(tmp_path):
    from novelforge.llm.cache import CachingLLM

    inner = MockLLM()
    inner.queue_json({"facts": []})
    cached = CachingLLM(inner, tmp_path / "c.jsonl")
    first = cached.generate_json("s", "p", SCHEMA)
    again = CachingLLM(MockLLM(), tmp_path / "c.jsonl").generate_json("s", "p", SCHEMA)
    assert first.data == again.data == {"facts": []}
    assert len(inner.calls) == 1
