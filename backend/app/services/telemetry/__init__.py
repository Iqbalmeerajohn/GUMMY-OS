"""Local telemetry — what a generation cost in energy and in money.

Distinct from ``app.observability`` (Langfuse traces, which can leave the
machine): nothing here is sent anywhere. It exists to make the project's
central claim measurable rather than asserted.
"""

from app.services.telemetry.energy import EnergyMeasurement, measure

__all__ = ["EnergyMeasurement", "measure"]
