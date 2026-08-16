"""Observability for GUMMY OS.

Two layers: local product-event logging (:mod:`analytics`) and optional LLM/agent
tracing (:mod:`langfuse`, off unless keys are set — point it at a self-hosted
instance to keep traces on the machine). Error reporting lives in
``app.core.observability``. All three are best-effort and never fail a request.
"""
