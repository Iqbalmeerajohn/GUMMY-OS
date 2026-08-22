"""Calibrate FILE_RETRIEVAL_MIN_SIMILARITY against a real embedding model.

The document-search sibling of ``calibrate_relevance.py``, which tunes the same
kind of floor for personal memories. The two are deliberately separate: document
chunks are longer and more topical than memory sentences, so their similarity
distributions differ and one threshold cannot serve both.

Runs the real extraction -> segmentation -> chunking pipeline over the fixture
documents below, embeds every chunk, and scores three classes of query/chunk
pair:

* relevant   - best similarity inside the document that answers the query
* distractor - best similarity in the OTHER documents for that same query
* no-answer  - best similarity anywhere for a query no document answers

The last class is the one the floor exists for. Sweeping the threshold over all
three shows what any given value costs in recall and buys in precision.

    python scripts/calibrate_retrieval_floor.py

Requires the Ollama daemon on localhost:11434 with the model pulled, and
EMBEDDINGS_PROVIDER=ollama. Reads nothing from the database. Re-run it whenever
the embedding model changes: a floor calibrated for one model says nothing about
another. Results as of the current model are recorded in docs/KNOWLEDGE_RAG.md
and pinned in tests/test_file_retrieval_calibration.py.
"""

import asyncio
import statistics
import sys

sys.path.insert(0, ".")

from app.services.embeddings.factory import get_embedding_service
from app.services.files.chunking_service import chunk_segments
from app.services.files.extraction_service import extract_segments

RESUME = """# Rehan Iqbal - Curriculum Vitae

## Education
B.Tech in Computer Science, 2021-2025. CGPA 8.7. Coursework covered data
structures, operating systems, compiler design and database internals.

## Experience
Backend engineering intern. Built REST services in Python and FastAPI, wrote
PostgreSQL migrations, and reduced p95 request latency from 400ms to 120ms by
adding query indexes and caching.

## Projects
GUMMY OS, a local-first personal AI operating system using PostgreSQL, pgvector
and Ollama. Implemented a BiLSTM sequence tagger for a named entity extraction
coursework project.

## Skills
Python, TypeScript, PostgreSQL, Docker, FastAPI, React.
"""

ARCH = """# GUMMY OS Architecture

## Memory System
Personal memories are embedded with nomic-embed-text and stored in pgvector.
Recall applies a relevance floor so that unrelated memories never enter a
prompt.

## Agent Orchestration
A deterministic keyword router picks a plan shape: SINGLE for one agent,
PIPELINE when one agent's output feeds the next, and PARALLEL when independent
agents can run concurrently and their results are synthesised.

## Retrieval
Document chunks are searched with hybrid retrieval: a vector query and a
Postgres full-text query, fused with reciprocal rank fusion.
"""

RECIPES = """# Kitchen Notes

## Sourdough
Feed the starter twelve hours before mixing. Hydration of seventy-five percent
gives an open crumb. Bake at 240C with steam for the first twenty minutes.

## Tomato Sauce
Soffritto of onion, carrot and celery cooked slowly in olive oil, then San
Marzano tomatoes simmered for forty minutes with a basil sprig.
"""

DOCS = {
    "Resume.md": RESUME,
    "Architecture.md": ARCH,
    "Kitchen.md": RECIPES,
}

# Queries whose answer genuinely lives in the named document.
GROUNDED = [
    ("what was my CGPA", "Resume.md"),
    ("which programming languages do I know", "Resume.md"),
    ("tell me about my internship", "Resume.md"),
    ("did I do anything with BiLSTM", "Resume.md"),
    ("what did I study at university", "Resume.md"),
    ("how much did I improve latency by", "Resume.md"),
    ("how does the agent router decide what to run", "Architecture.md"),
    ("what is reciprocal rank fusion used for here", "Architecture.md"),
    ("how are personal memories stored", "Architecture.md"),
    ("when do agents run in parallel", "Architecture.md"),
    ("what temperature do I bake bread at", "Kitchen.md"),
    ("how long does the tomato sauce simmer", "Kitchen.md"),
]

# Queries with no answer anywhere in the corpus. Every chunk is a false
# positive, which is exactly what the floor has to suppress.
UNGROUNDED = [
    "what is the capital of France",
    "who won the world cup in 1998",
    "explain the Krebs cycle",
    "what is the population of Jakarta",
    "how do I renew a passport in Canada",
    "what year did the Berlin Wall fall",
    "what is the tallest mountain in Africa",
    "how does photosynthesis work",
    "what are the symptoms of anaemia",
    "who wrote One Hundred Years of Solitude",
    "what is the exchange rate for the yen",
    "how many moons does Saturn have",
    "when is the next solar eclipse",
    "what is the offside rule in football",
    "how do I change a car tyre",
    "what is the boiling point of mercury",
    "who painted Guernica",
    "what is the speed of sound at sea level",
]


async def main() -> None:
    service = get_embedding_service()
    print("embedding model:", service.model_name)

    chunks = []  # (doc_name, text, vector)
    for name, body in DOCS.items():
        segments = extract_segments(
            data=body.encode("utf-8"), mime_type="text/markdown"
        )
        for sc in chunk_segments(segments, chunk_size=700, overlap=100):
            vec = await service.embed_query(sc.content)
            chunks.append((name, sc.content, vec))
    print("chunks embedded:", len(chunks))

    def cos(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb)

    relevant = []  # best similarity inside the target document
    distractor = []  # best similarity among non-target documents
    unrelated = []  # best similarity anywhere, for no-answer queries

    for query, target in GROUNDED:
        qv = await service.embed_query(query)
        sims_in = [cos(qv, v) for name, _, v in chunks if name == target]
        sims_out = [cos(qv, v) for name, _, v in chunks if name != target]
        relevant.append(max(sims_in))
        distractor.append(max(sims_out))

    for query in UNGROUNDED:
        qv = await service.embed_query(query)
        unrelated.append(max(cos(qv, v) for _, _, v in chunks))

    def describe(label: str, xs: list[float]) -> None:
        xs = sorted(xs)
        p25 = xs[max(0, len(xs) // 4)]
        p75 = xs[min(len(xs) - 1, 3 * len(xs) // 4)]
        print(
            f"{label:<12} n={len(xs):2d}  min={xs[0]:.3f}  p25={p25:.3f}  "
            f"median={statistics.median(xs):.3f}  p75={p75:.3f}  "
            f"max={xs[-1]:.3f}  mean={statistics.mean(xs):.3f}"
        )

    print()
    describe("relevant", relevant)
    describe("distractor", distractor)
    describe("unrelated", unrelated)

    print()
    print("--- no-answer queries, strongest first (these set the floor) ---")
    ranked = sorted(zip(UNGROUNDED, unrelated, strict=True), key=lambda p: -p[1])
    for query, sim in ranked[:5]:
        print(f"  {sim:.3f}  {query}")

    print()
    print("--- relevant pairs, weakest first ---")
    pairs = sorted(zip(GROUNDED, relevant, strict=True), key=lambda p: p[1])
    for (query, target), sim in pairs:
        print(f"  {sim:.3f}  {query:<46} -> {target}")

    print()
    print("thr   recall  prec   f1     distractors_kept  no_answer_kept")
    best: tuple[float, float, float, float] | None = None
    t = 0.44
    while t <= 0.5401:
        tp = sum(1 for s in relevant if s >= t)
        fp_d = sum(1 for s in distractor if s >= t)
        fp_u = sum(1 for s in unrelated if s >= t)
        fp = fp_d + fp_u
        recall = tp / len(relevant)
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        denom = recall + precision
        f1 = (2 * recall * precision / denom) if denom else 0.0
        print(
            f"{t:.2f}   {recall:.2f}    {precision:.2f}   {f1:.2f}   "
            f"{fp_d:2d}/{len(distractor):<2d}"
            f"             {fp_u:2d}/{len(unrelated):<2d}"
        )
        if best is None or f1 > best[1] + 1e-9:
            best = (t, f1, recall, precision)
        t += 0.01

    print()
    if best is not None:
        print(
            f"best f1 at threshold {best[0]:.2f} "
            f"(f1={best[1]:.2f} recall={best[2]:.2f} precision={best[3]:.2f})"
        )


asyncio.run(main())
