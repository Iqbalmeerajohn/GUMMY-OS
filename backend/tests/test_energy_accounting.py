"""Energy and cost accounting tests.

The measurement itself depends on hardware, so these concentrate on the two
things that must hold on *every* machine: it never fabricates a number it did
not measure, and it never breaks the generation it is measuring.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.telemetry.energy import (
    JOULES_PER_KWH,
    EnergyMeasurement,
    measure,
)


def _reading(
    joules: float | None,
    *,
    duration: float = 10.0,
    watts: float | None = None,
    samples: int = 1,
    basis: str = "gpu",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> EnergyMeasurement:
    """A measurement with everything but the interesting field defaulted."""
    return EnergyMeasurement(
        duration_seconds=duration,
        energy_joules=joules,
        average_watts=watts,
        peak_watts=None,
        samples=samples,
        basis=basis,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


async def test_measurement_reports_a_duration_even_when_disabled() -> None:
    async with measure(enabled=False) as reading:
        await asyncio.sleep(0.05)
        result = reading(prompt_tokens=10, completion_tokens=5)
    assert result.basis == "disabled"
    assert result.energy_joules is None
    assert result.duration_seconds > 0
    assert result.total_tokens == 15


async def test_no_counter_means_no_joules_not_a_guess() -> None:
    """The honesty property: absent hardware yields None, never an estimate."""
    async with measure(poll_ms=50) as reading:
        await asyncio.sleep(0.05)
        result = reading()
    if result.basis != "gpu":
        assert result.energy_joules is None
        assert result.average_watts is None


async def test_measurement_never_raises_into_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken sampler must not take down the generation it is watching."""

    def explode(_self: object) -> bool:
        raise RuntimeError("nvml is on fire")

    monkeypatch.setattr(
        "app.services.telemetry.energy._NvmlSampler._open", explode, raising=True
    )
    with pytest.raises(RuntimeError):
        # _open itself raising is a programming error we surface in tests...
        async with measure(poll_ms=50):
            pass


async def test_a_failing_power_read_loses_the_sample_not_the_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Individual sample failures are swallowed; the reading still completes."""
    monkeypatch.setattr(
        "app.services.telemetry.energy._NvmlSampler._open",
        lambda self: False,
        raising=True,
    )
    async with measure(poll_ms=20) as reading:
        await asyncio.sleep(0.05)
        result = reading(prompt_tokens=1, completion_tokens=1)
    assert result.basis == "unavailable"
    assert result.samples == 0


# ── cost arithmetic ──────────────────────────────────────────────────────────


def test_electricity_cost_converts_joules_to_kwh() -> None:
    one_kwh = _reading(JOULES_PER_KWH)
    assert one_kwh.electricity_usd(0.15) == pytest.approx(0.15)


def test_electricity_cost_is_none_without_a_measurement() -> None:
    assert _reading(None).electricity_usd(0.15) is None


def test_cloud_equivalent_prices_input_and_output_separately() -> None:
    """Output tokens cost several times input; a single rate would mislead."""
    reading = _reading(None, prompt_tokens=1_000_000, completion_tokens=1_000_000)
    cost = reading.cloud_equivalent_usd(
        input_usd_per_mtok=3.0, output_usd_per_mtok=15.0
    )
    assert cost == pytest.approx(18.0)


def test_saving_is_net_of_electricity() -> None:
    """The headline figure subtracts what the power actually cost."""
    reading = _reading(JOULES_PER_KWH, prompt_tokens=1_000_000, completion_tokens=0)
    summary = reading.as_dict(usd_per_kwh=0.15, input_rate=3.0, output_rate=15.0)
    assert summary["cloud_equivalent_usd"] == pytest.approx(3.0)
    assert summary["electricity_usd"] == pytest.approx(0.15)
    assert summary["saved_usd"] == pytest.approx(2.85)


def test_summary_is_json_safe_without_a_measurement() -> None:
    summary = _reading(None, basis="unavailable", samples=0).as_dict(
        usd_per_kwh=0.15, input_rate=3.0, output_rate=15.0
    )
    assert summary["energy_joules"] is None
    assert summary["basis"] == "unavailable"
    # A saving is still reportable from tokens alone; only the joules are lost.
    assert summary["saved_usd"] == 0.0
