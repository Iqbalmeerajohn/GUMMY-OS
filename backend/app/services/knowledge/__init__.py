"""Unified Knowledge & Retrieval Engine (M7).

One ranked context layer over the three knowledge sources — memories, goals,
files — so chat and (from M8) agents consume a single ``UnifiedKnowledgeContext``
instead of retrieving each source independently.

Pipeline: ``knowledge_retrieval_service`` fans out to the three sources (with
per-source graceful degradation), ``knowledge_ranker`` fuses them onto one
comparable scale, and ``knowledge_context_builder`` compresses the result into a
token-budgeted ``<knowledge>`` prompt block with source attribution preserved.
"""
