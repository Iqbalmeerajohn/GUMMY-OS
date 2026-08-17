"""Memory extraction must survive what a small local model actually emits.

Found by running the real stack, not the suite: with ``qwen2.5:3b`` every
extraction failed with "could not parse LLM output as JSON", so nothing was ever
remembered. The model returned

    [{"content": "Iqbal lives in Bangalore", "category": "profile}]

— one missing quote. ``json.loads`` raised, the batch was discarded, and the
product's central promise silently stopped working with no error surfaced.

Two defences, tested here: constrained decoding via ``SupportsJsonMode`` (which
makes the malformation impossible at the source) and a salvage pass for
providers that cannot constrain.
"""

from __future__ import annotations

from typing import Any

from app.models.enums import MemoryCategory
from app.services.conversation.memory_extraction_service import (
    _parse_candidates,
    _salvage,
)
from app.services.llm.base import LLMResponse, SupportsJsonMode
from app.services.llm.ollama_gateway import OllamaGateway


def _gateway() -> OllamaGateway:
    return OllamaGateway(
        base_url="http://localhost:11434",
        default_model="qwen2.5:3b",
        max_tokens=512,
        timeout=5.0,
        keep_alive="30m",
    )


# ── The capability ───────────────────────────────────────────────────────────


def test_ollama_gateway_advertises_json_mode() -> None:
    assert isinstance(_gateway(), SupportsJsonMode)


def test_json_mode_sets_the_ollama_format_field() -> None:
    """``format: json`` is what constrains sampling to valid JSON."""
    gateway = _gateway()
    messages = [{"role": "user", "content": "hi"}]

    plain = gateway._payload(messages, "m", 128, stream=False)
    constrained = gateway._payload(messages, "m", 128, stream=False, json_mode=True)

    assert "format" not in plain
    assert constrained["format"] == "json"


def test_streaming_payload_is_unaffected() -> None:
    gateway = _gateway()
    payload = gateway._payload(
        [{"role": "user", "content": "hi"}], "m", 128, stream=True
    )
    assert payload["stream"] is True
    assert "format" not in payload


# ── Parsing what the model really returns ───────────────────────────────────


def test_parses_a_bare_object_not_only_an_array() -> None:
    """Observed live: JSON mode returns one object rather than a list."""
    text = '{"content": "Lives in Bangalore", "category": "profile"}'

    assert _parse_candidates(text) == [(MemoryCategory.PROFILE, "Lives in Bangalore")]


def test_parses_a_list_wrapped_in_a_key() -> None:
    text = (
        '{"memories": [{"content": "Lives in Bangalore", "category": "profile"},'
        '{"content": "Favorite sport is football", "category": "preference"}]}'
    )

    assert _parse_candidates(text) == [
        (MemoryCategory.PROFILE, "Lives in Bangalore"),
        (MemoryCategory.PREFERENCE, "Favorite sport is football"),
    ]


def test_empty_object_stores_nothing() -> None:
    """An unrelated turn yields ``{}`` — correctly nothing to remember."""
    assert _parse_candidates("{}") == []


def test_plain_array_still_parses() -> None:
    text = '[{"content": "Name is Iqbal", "category": "profile"}]'
    assert _parse_candidates(text) == [(MemoryCategory.PROFILE, "Name is Iqbal")]


def test_fenced_json_still_parses() -> None:
    text = '```json\n[{"content": "Name is Iqbal", "category": "profile"}]\n```'
    assert _parse_candidates(text) == [(MemoryCategory.PROFILE, "Name is Iqbal")]


# ── Salvage: the exact bytes that broke production ──────────────────────────


def test_salvages_the_real_malformed_output() -> None:
    """The literal string qwen2.5:3b produced, missing its closing quote."""
    broken = '[{"content": "Iqbal lives in Bangalore", "category": "profile}]'

    assert _parse_candidates(broken) == [
        (MemoryCategory.PROFILE, "Iqbal lives in Bangalore")
    ]


def test_salvage_recovers_multiple_items() -> None:
    broken = (
        '[{"content": "Name is Iqbal", "category": "profile},'
        '{"content": "Building GUMMY", "category": "project}]'
    )

    assert _salvage(broken) == [
        {"content": "Name is Iqbal", "category": "profile"},
        {"content": "Building GUMMY", "category": "project"},
    ]


def test_salvage_yields_nothing_for_prose() -> None:
    """A model that answers in prose must not be mined for phantom facts."""
    assert _salvage("I could not find anything worth remembering.") == []
    assert _parse_candidates("I could not find anything worth remembering.") == []


def test_salvaged_items_still_pass_the_quality_filter() -> None:
    """Recovery must not bypass the low-quality guard."""
    broken = '[{"content": "User is asking about Vizag", "category": "profile}]'

    assert _parse_candidates(broken) == []


def test_salvaged_items_still_validate_the_category() -> None:
    broken = '[{"content": "Lives in Bangalore", "category": "nonsense}]'

    assert _parse_candidates(broken) == []


# ── The extraction call selects JSON mode when it is available ──────────────


class _RecordingJsonLLM:
    """Records which entrypoint the extraction service chose."""

    name = "recording"

    def __init__(self) -> None:
        self.used_json_mode = False

    async def generate(self, **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            text="[]", model="m", input_tokens=1, output_tokens=1, stop_reason="stop"
        )

    async def generate_json(self, **kwargs: Any) -> LLMResponse:
        self.used_json_mode = True
        return LLMResponse(
            text='{"content": "Lives in Bangalore", "category": "profile"}',
            model="m",
            input_tokens=1,
            output_tokens=1,
            stop_reason="stop",
        )


def test_recording_llm_satisfies_the_protocol() -> None:
    assert isinstance(_RecordingJsonLLM(), SupportsJsonMode)
