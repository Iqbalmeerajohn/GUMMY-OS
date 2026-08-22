"""Measure the document RAG pipeline against real Postgres and real Ollama.

Reports extraction, chunking, embedding, persistence and each retrieval layer
separately, because they fail and improve for different reasons: chunking is
CPU-bound and sub-millisecond, embedding is a network round trip that dominates
indexing, and retrieval is a database query whose cost depends on the indexes
being used.

Two measurement traps this deliberately avoids:

* The fixture document repeats itself, which would produce identical chunks and
  let the embedding cache answer most calls. Each repetition is made textually
  distinct so "embedding latency" measures inference, not a dict lookup.
* Query embeddings are cached, so cold and warm calls are reported separately
  rather than blended into one median that describes neither.

    EMBEDDINGS_PROVIDER=ollama python scripts/benchmark_rag.py

Requires Ollama on localhost:11434 and the configured PostgreSQL. Creates a
throwaway user and deletes it, along with its files, on the way out.
"""

import asyncio
import os
import statistics
import sys
import time
import uuid

sys.path.insert(0, ".")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "ollama")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.tenant_context import set_current_user_id
from app.database.session import get_sessionmaker
from app.services.embeddings.factory import get_embedding_service
from app.services.files import file_context_service
from app.services.files.chunking_service import chunk_segments
from app.services.files.extraction_service import extract_segments
from app.services.files.file_retrieval_service import file_retrieval_service
from app.services.files.hybrid_retrieval import search as hybrid_search

DOC = (
    """# Engineering Handbook

## Deployment
Services deploy through a blue-green rollout. The health check must pass for
sixty seconds before traffic shifts. Rollback is automatic on a 5xx rate above
two percent.

## Incident Response
Sev-1 pages the on-call immediately. The incident commander owns comms, not the
fix. Post-mortems are blameless and due within five working days.

## Data Retention
Application logs are kept for thirty days, audit logs for seven years, and
backups are tested by restore every quarter.

## Access Control
Production access requires hardware MFA. Break-glass credentials live in the
vault and their use pages the security team automatically.
"""
    * 6
)

# Make every repetition textually distinct so no two chunks collide in the
# embedding cache; otherwise "embedding latency" measures a dict lookup.
DOC = "\n".join(
    f"{line} [para {i // 20}]" if line.strip() else line
    for i, line in enumerate(DOC.splitlines())
)

QUERIES = [
    "how long are audit logs kept",
    "what happens when the error rate spikes",
    "who owns communication during an incident",
    "what is required for production access",
    "when are post-mortems due",
]


def sessions() -> async_sessionmaker[AsyncSession]:
    """The session factory, or a clear failure if no database is configured."""
    maker = get_sessionmaker()
    if maker is None:
        raise SystemExit("No DATABASE_URL configured; this benchmark needs Postgres.")
    return maker


def ms(t: float) -> str:
    return f"{t * 1000:.1f} ms"


def stat(label: str, samples: list[float]) -> None:
    s = sorted(samples)
    print(
        f"  {label:<42} n={len(s):2d}  median={ms(statistics.median(s))}"
        f"   p95={ms(s[min(len(s) - 1, int(len(s) * 0.95))])}   max={ms(s[-1])}"
    )


async def main() -> None:
    uid = uuid.uuid4()
    set_current_user_id(uid)
    embed = get_embedding_service()
    data = DOC.encode("utf-8")
    print(f"document: {len(data):,} bytes\n")

    # ── extraction + chunking (CPU only) ─────────────────────────────────────
    ex: list[float] = []
    ch: list[float] = []
    for _ in range(5):
        t = time.perf_counter()
        segs = extract_segments(data=data, mime_type="text/markdown")
        ex.append(time.perf_counter() - t)
        t = time.perf_counter()
        chunks = list(chunk_segments(segs, chunk_size=700, overlap=100))
        ch.append(time.perf_counter() - t)
    print("PIPELINE")
    stat("extraction (markdown -> segments)", ex)
    stat("chunking (segments -> chunks)", ch)
    print(f"  {'segments / chunks produced':<42} {len(segs)} / {len(chunks)}")

    # ── embedding ────────────────────────────────────────────────────────────
    emb: list[float] = []
    for c in chunks:
        t = time.perf_counter()
        await embed.embed_query(c.content)
        emb.append(time.perf_counter() - t)
    stat("embedding, per chunk (Ollama)", emb)
    print(
        f"  {'embedding, whole document':<42} {ms(sum(emb))} for {len(chunks)} chunks"
    )

    async with sessions()() as s:
        await s.execute(
            text(
                "INSERT INTO users (id,email,password_hash,created_at,updated_at)"
                " VALUES (:i,:e,'x',now(),now())"
            ),
            {"i": uid, "e": f"perf-{uid.hex[:8]}@phase-n.test"},
        )
        fid = uuid.uuid4()
        await s.execute(
            text(
                "INSERT INTO files (id, user_id, filename, original_filename,"
                " mime_type, size_bytes, storage_path, upload_status,"
                " processing_status, chunk_count, indexed_at, created_at,"
                " updated_at) VALUES (:i, :u, 'handbook.md', 'handbook.md',"
                " 'text/markdown', :n, 'x', 'uploaded', 'completed', :c,"
                " now(), now(), now())"
            ),
            {"i": fid, "u": uid, "n": len(data), "c": len(chunks)},
        )
        t = time.perf_counter()
        for i, c in enumerate(chunks):
            await s.execute(
                text(
                    "INSERT INTO file_chunks (id, user_id, file_id,"
                    " chunk_index, content, token_count, embedding,"
                    " embedding_model, created_at) VALUES (:i, :u, :f, :x,"
                    " :c, 10, CAST(:e AS vector), 'nomic-embed-text', now())"
                ),
                {
                    "i": uuid.uuid4(),
                    "u": uid,
                    "f": fid,
                    "x": i,
                    "c": c.content,
                    "e": str(await embed.embed_query(c.content)),
                },
            )
        await s.commit()
        took = ms(time.perf_counter() - t)
        label = "persist chunks + vectors"
        print(f"  {label:<42} {took} for {len(chunks)} chunks")

    print("\nRETRIEVAL (warm, 5 queries x 4 runs)")
    async with sessions()() as s:
        vec_only: list[float] = []
        hybrid_full: list[float] = []
        ctx_full: list[float] = []
        qembed: list[float] = []
        qembed_warm: list[float] = []
        for run in range(4):
            for base in QUERIES:
                # Run 0 is cold (never-seen text); later runs repeat it, which
                # is what a real session looks like once the cache is warm.
                # Run 0 embeds text never seen before; run 1 embeds the base
                # query for the first time (also cold). Only runs 2+ are true
                # cache hits, and mislabelling run 1 as warm would put a real
                # Ollama call into the cache-hit distribution.
                q = f"{base} (variant {run})" if run == 0 else base
                t = time.perf_counter()
                qv = await embed.embed_query(q)
                dt = time.perf_counter() - t
                (qembed_warm if run >= 2 else qembed).append(dt)
                t = time.perf_counter()
                await hybrid_search(s, user_id=uid, query=q, query_vector=qv, limit=5)
                vec_only.append(time.perf_counter() - t)
                t = time.perf_counter()
                await file_retrieval_service.hybrid_search(
                    s, user_id=uid, query=q, limit=5
                )
                hybrid_full.append(time.perf_counter() - t)
                t = time.perf_counter()
                await file_context_service.retrieve_file_context(
                    s, user_id=uid, query=q
                )
                ctx_full.append(time.perf_counter() - t)
        stat("query embedding, cold (Ollama call)", qembed)
        stat("query embedding, warm (cache hit)", qembed_warm)
        stat("hybrid search, SQL only (vector+FTS+RRF)", vec_only)
        stat("hybrid search, incl. query embedding", hybrid_full)
        stat("full chat grounding (search + inventory)", ctx_full)

    async with sessions()() as s:
        await s.execute(text("DELETE FROM file_chunks WHERE user_id=:u"), {"u": uid})
        await s.execute(text("DELETE FROM files WHERE user_id=:u"), {"u": uid})
        await s.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
        await s.commit()


asyncio.run(main())
