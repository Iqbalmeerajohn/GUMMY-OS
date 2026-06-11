"""Agent handlers — pure ``AgentTask -> AgentResult`` functions.

Each built-in agent registers a manifest (manifests.py) and implements one
handler here. Handlers never persist, never commit, and never execute
actions; they reason over the task's context pack and return proposals
(PHASE3_PLAN.md §9/§12).
"""
