"""Files System (M6) — upload, storage, extraction, chunking, retrieval.

A complete file-management layer, not just blob storage: files are uploaded
through a provider-agnostic storage seam, their text is extracted and chunked
deterministically, and the chunks become the reusable substrate for future RAG,
agents, and workspace features. See PHASE5_PLAN / M6.
"""
