"""Measuring what a local generation actually cost — in joules and in money.

The claim on the front of this project is that running your own model is
cheaper and yours. "Yours" is architectural and already true. "Cheaper" is an
empirical claim, and until something measures it, it is marketing.

So this samples real GPU power while a generation runs and integrates it into
joules, rather than multiplying tokens by a constant. Two reasons that matters:
a partly CPU-offloaded model draws a very different power profile from one
resident in VRAM, and idle draw is not free — a card sitting at 30 W for a
twenty-second generation costs something a token-count model cannot see.

What it deliberately does **not** do is pretend to precision it lacks:

* Only the GPU rail is measured. CPU and DRAM draw are real and not counted,
  so a reported figure is a floor, not a total. That is stated in the output
  as ``basis``, not hidden.
* Idle draw is included, not subtracted. Attributing only the delta above idle
  would flatter local inference by pretending the card would have been off.
* Without an NVIDIA GPU, or without ``pynvml``, there are simply no joules.
  Token accounting still works and ``energy_joules`` is None — never a
  fabricated estimate.

The cloud comparison is explicitly a *counterfactual*: what these same token
counts would have cost at a hosted frontier model's published rate. It is not
a claim about quality parity, and the rates are configuration because they go
stale.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

JOULES_PER_KWH = 3_600_000.0


@dataclass(frozen=True)
class EnergyMeasurement:
    """What one generation drew, and what it would have cost elsewhere."""

    duration_seconds: float
    # None when no GPU counter was available — never a guess.
    energy_joules: float | None
    average_watts: float | None
    peak_watts: float | None
    samples: int
    basis: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def electricity_usd(self, usd_per_kwh: float) -> float | None:
        if self.energy_joules is None:
            return None
        return (self.energy_joules / JOULES_PER_KWH) * usd_per_kwh

    def cloud_equivalent_usd(
        self, *, input_usd_per_mtok: float, output_usd_per_mtok: float
    ) -> float:
        """What a hosted frontier model would have charged for these tokens."""
        return (
            self.prompt_tokens / 1_000_000.0 * input_usd_per_mtok
            + self.completion_tokens / 1_000_000.0 * output_usd_per_mtok
        )

    def as_dict(
        self, *, usd_per_kwh: float, input_rate: float, output_rate: float
    ) -> dict:
        """A JSON-safe summary for the API and the UI."""
        electricity = self.electricity_usd(usd_per_kwh)
        cloud = self.cloud_equivalent_usd(
            input_usd_per_mtok=input_rate, output_usd_per_mtok=output_rate
        )
        return {
            "duration_seconds": round(self.duration_seconds, 3),
            "energy_joules": (
                round(self.energy_joules, 2) if self.energy_joules is not None else None
            ),
            "average_watts": (
                round(self.average_watts, 1) if self.average_watts is not None else None
            ),
            "peak_watts": (
                round(self.peak_watts, 1) if self.peak_watts is not None else None
            ),
            "samples": self.samples,
            "basis": self.basis,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "electricity_usd": (
                round(electricity, 8) if electricity is not None else None
            ),
            "cloud_equivalent_usd": round(cloud, 6),
            # The headline: what running locally did not cost. Electricity is
            # subtracted when known, so the figure is a net saving, not a
            # gross one that ignores the power bill.
            "saved_usd": round(cloud - (electricity or 0.0), 6),
        }


class _NvmlSampler:
    """Polls NVIDIA GPU power draw. Returns no samples when unavailable."""

    def __init__(self, poll_ms: int) -> None:
        self._poll_seconds = max(0.02, poll_ms / 1000.0)
        self._watts: list[float] = []
        self._task: asyncio.Task[None] | None = None
        self._handle = None
        self._pynvml = None

    def _open(self) -> bool:
        try:
            import pynvml
        except ImportError:
            return False
        try:
            pynvml.nvmlInit()
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._pynvml = pynvml
            return True
        except Exception:
            # A driver mismatch or a machine with no NVIDIA card. Not an
            # error worth a stack trace on every generation.
            return False

    def _close(self) -> None:
        if self._pynvml is not None:
            with contextlib.suppress(Exception):
                self._pynvml.nvmlShutdown()
        self._pynvml = None
        self._handle = None

    async def _poll(self) -> None:
        assert self._pynvml is not None
        while True:
            try:
                milliwatts = self._pynvml.nvmlDeviceGetPowerUsage(self._handle)
                self._watts.append(milliwatts / 1000.0)
            except Exception:
                # Lose the sample, not the measurement.
                pass
            await asyncio.sleep(self._poll_seconds)

    async def __aenter__(self) -> _NvmlSampler:
        if self._open():
            self._task = asyncio.create_task(self._poll())
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._close()

    @property
    def watts(self) -> list[float]:
        return self._watts


# What the context manager hands the caller: call it when the generation is
# done, with the token counts, to get the finished reading.
Reading = Callable[..., EnergyMeasurement]


@contextlib.asynccontextmanager
async def measure(
    *, poll_ms: int = 100, enabled: bool = True
) -> AsyncIterator[Reading]:
    """Measure a generation. Yields a callable that finalises the reading.

        async with measure() as reading:
            response = await llm.generate(...)
            result = reading(prompt_tokens=..., completion_tokens=...)

    Measurement never affects the thing being measured: any failure inside
    here degrades to "no joules", and nothing raises into the caller.
    """
    if not enabled:
        started = time.perf_counter()

        def _disabled(
            prompt_tokens: int = 0, completion_tokens: int = 0
        ) -> EnergyMeasurement:
            return EnergyMeasurement(
                duration_seconds=time.perf_counter() - started,
                energy_joules=None,
                average_watts=None,
                peak_watts=None,
                samples=0,
                basis="disabled",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        yield _disabled
        return

    sampler = _NvmlSampler(poll_ms)
    started = time.perf_counter()
    async with sampler:

        def finalise(
            prompt_tokens: int = 0, completion_tokens: int = 0
        ) -> EnergyMeasurement:
            duration = time.perf_counter() - started
            watts = list(sampler.watts)
            if not watts:
                return EnergyMeasurement(
                    duration_seconds=duration,
                    energy_joules=None,
                    average_watts=None,
                    peak_watts=None,
                    samples=0,
                    basis="unavailable",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            average = sum(watts) / len(watts)
            return EnergyMeasurement(
                duration_seconds=duration,
                # Rectangular integration over a uniform sample interval:
                # average power times elapsed wall time. The samples are
                # evenly spaced by construction, so this is exact to the
                # sampling resolution.
                energy_joules=average * duration,
                average_watts=average,
                peak_watts=max(watts),
                samples=len(watts),
                basis="gpu",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        yield finalise
