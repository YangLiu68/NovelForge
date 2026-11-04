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
from novelforge.llm.openrouter_backend import OpenRouterLLM, price_key

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


def _openrouter(handler):
    return OpenRouterLLM(
        "anthropic/claude-opus-5.5", "sk-or-test", "http://or.test/api/v1",
        transport=httpx.MockTransport(handler),
    )  # fmt: skip


def test_openrouter_backend_json_and_stream():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        assert request.headers["authorization"] == "Bearer sk-or-test"
        assert body["model"] == "anthropic/claude-opus-5.5"
        assert body["provider"] == {"require_parameters": True}
        if body.get("stream"):
            events = [
                {"choices": [{"delta": {"content": "Fog "}}]},
                {"choices": [{"delta": {"content": "rolled in."}, "finish_reason": "stop"}]},
                {
                    "choices": [],
                    "usage": {"prompt_tokens": 40, "completion_tokens": 4, "cost": 0.01},
                },
            ]
            text = (
                ": OPENROUTER PROCESSING\n\n"
                + "".join(f"data: {json.dumps(e)}\n\n" for e in events)
                + "data: [DONE]\n\n"
            )
            return httpx.Response(200, text=text)
        fmt = body["response_format"]
        assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
        assert "title" not in fmt["json_schema"]["schema"]
        return httpx.Response(
            200,
            json={
                "id": "gen-1",
                "model": "anthropic/claude-opus-5.5",
                "choices": [{"message": {"content": '{"facts": []}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1200, "completion_tokens": 300},
            },
        )

    llm = _openrouter(handler)
    result = llm.generate_json("s", "p", SCHEMA)
    assert result.data == {"facts": []} and result.request_id == "gen-1"
    # No billed cost in the response: fall back to the local price table.
    assert result.cost_usd == pytest.approx(1200 / 1e6 * 4 + 300 / 1e6 * 20)
    assert seen[0]["reasoning"] == {"effort": "medium"}
    chunks = list(llm.stream_text("s", "p"))
    assert "".join(c.text for c in chunks) == "Fog rolled in."
    final = chunks[-1].result
    assert chunks[-1].done and final.output_tokens == 4 and final.cost_usd == 0.01


def _choice(content, finish):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}]}


@pytest.mark.parametrize(
    "status,payload,kind",
    [
        (200, _choice("{", "length"), "max_tokens"),
        (200, _choice("", "content_filter"), "refusal"),
        (200, _choice("{not json", "stop"), "invalid_json"),
        (401, {"error": {"code": 401, "message": "No auth"}}, "config"),
        (402, {"error": {"code": 402, "message": "Insufficient credits"}}, "config"),
        (429, {"error": {"code": 429, "message": "Rate limited"}}, "transport"),
    ],
)
def test_openrouter_backend_errors(status, payload, kind):
    llm = _openrouter(lambda request: httpx.Response(status, json=payload))
    with pytest.raises(LLMError) as exc:
        llm.generate_json("s", "p", SCHEMA)
    assert exc.value.kind == kind


def test_openrouter_needs_a_key_and_maps_prices():
    with pytest.raises(LLMError) as exc:
        OpenRouterLLM("anthropic/claude-opus-5.5", "")
    assert exc.value.kind == "config"
    assert price_key("anthropic/claude-opus-5.5") == "claude-opus-5-5"


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


def test_caching_llm_replays_repeatable_failures_only(tmp_path):
    from novelforge.llm.base import LLMError
    from novelforge.llm.cache import CachingLLM

    class Failing(MockLLM):
        def __init__(self, kind):
            super().__init__()
            self.kind = kind

        def generate_json(self, system, prompt, schema, max_tokens=16000):
            self.calls.append(prompt)
            raise LLMError(self.kind, "output hit num_predict=2048")

    capped = Failing("max_tokens")
    for llm in (capped, MockLLM()):  # the second run never reaches the model
        with pytest.raises(LLMError) as err:
            CachingLLM(llm, tmp_path / "c.jsonl").generate_json("s", "p", SCHEMA)
        assert err.value.kind == "max_tokens" and "2048" in str(err.value)
    assert len(capped.calls) == 1

    down = Failing("transport")
    with pytest.raises(LLMError):
        CachingLLM(down, tmp_path / "t.jsonl").generate_json("s", "p", SCHEMA)
    assert not (tmp_path / "t.jsonl").exists()


XUE = CharacterRef("x", "林雪棠", ("雪棠",), {"pronoun": "she"})
ZH = ChapterRef("z1", 2, "雾港", "林雪棠今年十七岁，一双琥珀色的眼睛。\n\n她惯用左手。", 1, 10)


def test_chinese_chapters_get_the_chinese_prompt_and_schema():
    from novelforge.extraction.prompt import PROMPT_VERSION_ZH, SYSTEM_ZH, user_prompt

    llm = MockLLM()
    llm.queue_json({"facts": []})
    run = extract_with_llm(ZH, [XUE], llm)
    call = llm.calls[0]
    system, prompt, schema = call["system"], call["prompt"], call["schema"]
    assert system == SYSTEM_ZH and run.prompt_version == PROMPT_VERSION_ZH
    assert "presence" in schema["properties"]["facts"]["items"]["properties"]["kind"]["enum"]
    assert user_prompt(ZH, [XUE], ZH.body).startswith("人物：\n- 林雪棠（又称：雪棠）")
    assert "故事第 10 天" in prompt


def test_chinese_values_are_normalised_and_grounded():
    llm = MockLLM()
    llm.queue_json(
        {
            "facts": [
                fact(subject="林雪棠", kind="age", value="17", quote="林雪棠今年十七岁"),
                fact(subject="雪棠", kind="eye_color", value="琥珀色", quote="一双琥珀色的眼睛"),
                fact(subject="林雪棠", kind="handedness", value="left", quote="她惯用左手"),
                fact(subject="林雪棠", kind="presence", value="present", quote="她惯用左手"),
                # Values the quote does not state.
                fact(subject="林雪棠", kind="age", value="18", quote="林雪棠今年十七岁"),
                fact(subject="林雪棠", kind="eye_color", value="碧绿", quote="一双琥珀色的眼睛"),
                fact(subject="林雪棠", kind="eye_color", value="像秋水", quote="一双琥珀色的眼睛"),
            ]
        }
    )
    run = extract_with_llm(ZH, [XUE], llm)
    got = {(c.predicate, c.value) for c in run.claims}
    assert got == {("age", "17"), ("eye_color", "amber"), ("handedness", "left"),
                   ("presence", "present")}  # fmt: skip
    assert sorted(r["reason"] for r in run.rejected) == [
        "malformed value", "value not in quote", "value not in quote",
    ]  # fmt: skip


def test_presence_is_chinese_only():
    llm = MockLLM()
    llm.queue_json({"facts": [fact(kind="presence", value="present")]})
    run = extract_with_llm(CH, [MARA, TOMAS], llm)
    assert run.claims == [] and run.rejected[0]["reason"] == "unknown kind"


def test_rules_backed_mock_reads_the_chinese_prompt():
    run = extract_with_llm(ZH, [XUE], rules_backed_mock())
    rules = extract_claims(ZH, [XUE])
    as_set = lambda cs: {(c.predicate, c.value, c.modality, c.spans[0].start) for c in cs}  # noqa: E731
    assert run.rejected == [] and as_set(run.claims) <= as_set(rules)
    assert ("eye_color", "amber") in {(c.predicate, c.value) for c in run.claims}


def test_chinese_windows_count_characters():
    body = "\n\n".join("林" * 400 for _ in range(4))
    assert len(windows(body, max_words=500)) == 2


def test_a_hair_change_the_text_explains_is_marked():
    body = "沈鸢原本一头黑发。\n\n后来沈鸢那头染过的发剪掉了，如今是一头银发。"
    ch = ChapterRef("z2", 3, "", body, 1, 5)
    cast = [CharacterRef("s", "沈鸢")]
    llm = MockLLM()
    llm.queue_json(
        {
            "facts": [
                fact(subject="沈鸢", kind="hair_color", value="黑", quote="沈鸢原本一头黑发"),
                fact(subject="沈鸢", kind="hair_color", value="银", object="change",
                     quote="如今是一头银发"),
            ]
        }
    )  # fmt: skip
    run = extract_with_llm(ch, cast, llm)
    assert [c.details.get("change", False) for c in run.claims] == [False, True]
