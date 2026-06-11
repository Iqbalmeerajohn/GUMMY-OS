"""Tool Execution Interface (Phase 3, M6) — the single gated door to tools.

Agents never call SDKs or services directly; every capability flows through
``interface.invoke`` which enforces the manifest check, the Policy Engine's
Green/Yellow/Red gate, and a complete ``tool_invocations`` audit trail.
Phase 3 ships **Green executors only**; Yellow/Red tools are modeled and
gated but never executed (PHASE3_PLAN.md §10).
"""
