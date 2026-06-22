"""Observability integrations for GUMMY OS.

Houses the Langfuse LLM/agent tracing layer. Sentry error monitoring lives in
``app.core.observability`` (kept there for historical reasons); both are
best-effort and fully disabled when their credentials are absent.
"""
