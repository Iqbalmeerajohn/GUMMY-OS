"""Agent Framework services (Phase 3).

The Master Orchestrator and its components live here. Nothing in the memory
or conversation domains imports this package at module level — the single
composition point is a lazy, flag-gated branch inside
``conversation_turn_service.run_turn`` (see PHASE3_PLAN.md §4.7).
"""
