"""Calibrate RETRIEVAL_MIN_SEMANTIC_SIMILARITY against a real embedding model.

Measures the cosine-similarity separation between relevant and irrelevant
(query, memory) pairs using the exact call ``OllamaEmbeddingProvider`` makes, so
the number in ``app.core.constants`` is derived from data rather than guessed.

Run it whenever the embedding model changes — a threshold calibrated for one
model says nothing about another, because each has its own similarity baseline.

    python scripts/calibrate_relevance.py

Requires the Ollama daemon on localhost:11434 with the model pulled. Reads
nothing from the database; MEMORIES below is a fixture you should replace with a
sample of the store you are tuning for.
"""

import json
import urllib.request

OLLAMA = "http://localhost:11434/api/embed"
MODEL = "nomic-embed-text"

MEMORIES = [
    "user may need to set up basic test environments for their development environment",
    "user needs to focus on initial design and foundational coding for GUMMY",
    "Favorite sport is football",
    "Iqbal lives in Bangalore",
    "Lives in Vizag, India",
    "Name is Iqbal",
    "Building GUMMY, a personal AI operating system",
    "Building GUMMY, a personal AI operating system is a current project.",
    "GUMMY OS is something Iqbal is building",
]

# (query, indices of memories that SHOULD be considered relevant)
PROBES = [
    ("where do I live?", {3, 4}),
    ("what is my name?", {5}),
    ("what am I building?", {1, 6, 7, 8}),
    ("what is my favourite sport?", {2}),
    ("tell me about my project", {1, 6, 7, 8}),
    # Deliberately unrelated — nothing stored should be injected for these.
    ("how do I bake a chocolate cake?", set()),
    ("what is the capital of France?", set()),
    ("explain the quicksort algorithm", set()),
    ("write a python function that reverses a string", set()),
    ("what is the weather tomorrow?", set()),
    ("summarise the theory of relativity", set()),
]


def embed(texts: list[str]) -> list[list[float]]:
    req = urllib.request.Request(
        OLLAMA,
        data=json.dumps({"model": MODEL, "input": texts}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310
        vectors: list[list[float]] = json.loads(r.read())["embeddings"]
    return vectors


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb)


mem_vecs = embed(MEMORIES)
q_vecs = embed([p[0] for p in PROBES])

relevant_scores = []
irrelevant_scores = []

print(f"{'query':<46} {'best-relevant':>14} {'best-irrelevant':>16}")
print("-" * 80)
for (query, rel_idx), qv in zip(PROBES, q_vecs, strict=True):
    sims = [cosine(qv, mv) for mv in mem_vecs]
    rel = [s for i, s in enumerate(sims) if i in rel_idx]
    irr = [s for i, s in enumerate(sims) if i not in rel_idx]
    relevant_scores += rel
    irrelevant_scores += irr
    br = f"{max(rel):.4f}" if rel else "   —  "
    bi = f"{max(irr):.4f}" if irr else "   —  "
    print(f"{query:<46} {br:>14} {bi:>16}")

print("-" * 80)
print(
    f"RELEVANT   pairs: n={len(relevant_scores):3d}  "
    f"min={min(relevant_scores):.4f}  "
    f"mean={sum(relevant_scores)/len(relevant_scores):.4f}  "
    f"max={max(relevant_scores):.4f}"
)
print(
    f"IRRELEVANT pairs: n={len(irrelevant_scores):3d}  "
    f"min={min(irrelevant_scores):.4f}  "
    f"mean={sum(irrelevant_scores)/len(irrelevant_scores):.4f}  "
    f"max={max(irrelevant_scores):.4f}"
)

# The separating band: above the best irrelevant, below the worst relevant.
print()
print(f"worst RELEVANT   = {min(relevant_scores):.4f}")
print(f"best  IRRELEVANT = {max(irrelevant_scores):.4f}")
gap = min(relevant_scores) - max(irrelevant_scores)
print(
    f"separation gap   = {gap:+.4f}  "
    f"({'clean' if gap > 0 else 'OVERLAP — no perfect threshold exists'})"
)

# How each candidate threshold performs.
print()
print(f"{'floor':>6} {'relevant kept':>14} {'irrelevant kept':>16}")
for t in [0.45, 0.50, 0.55, 0.58, 0.60, 0.62, 0.65, 0.70, 0.75]:
    rk = sum(1 for s in relevant_scores if s >= t)
    ik = sum(1 for s in irrelevant_scores if s >= t)
    n_rel, n_irr = len(relevant_scores), len(irrelevant_scores)
    print(f"{t:>6.2f} {rk:>7}/{n_rel:<6} {ik:>8}/{n_irr:<7}")
