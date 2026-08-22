# Document Knowledge & Hybrid Retrieval (RAG 2.0)

How GUMMY answers questions from the user's own documents, and why each part
works the way it does.

Personal memory and document knowledge are separate systems throughout. A
memory is something GUMMY learned about the user across conversations; a
document is a file they uploaded. They have different lifecycles, different
trust properties and different relevance floors, and mixing them would make
both harder to reason about. They meet only at the end, in the unified
knowledge block that goes to the model, where each item is labelled with where
it came from.

---

## The pipeline

```
upload → checksum → extract → segment → chunk → embed → index
                                                          ↓
query → normalize → (vector ∥ full-text) → RRF fuse → gate → cite
```

### Checksum

Upload hashes the bytes with SHA-256 and returns the existing file when that
hash already exists for that user. Re-uploading the same document should not
produce a second copy that splits search results between them.

The uniqueness constraint is `(user_id, checksum)`, not `checksum` alone. Two
people owning the same document is normal, and a global constraint would both
collapse them and leak the fact that someone else holds that file.

### Extract and segment

Extraction produces `DocumentSegment`s rather than one flat string, because the
flattened version threw away the only thing that makes a citation checkable —
where in the document the text came from.

| Format   | Segment boundary | Provenance recorded |
|----------|------------------|---------------------|
| PDF      | page             | `page` |
| Markdown | heading          | `section` |
| CSV      | 25-row block     | `row_start`, `row_end`, `header` |
| TXT/DOCX | whole document   | none |

Plain text records nothing, and that is deliberate: a format with no internal
structure has no page number, and inventing one would be worse than admitting
there is none.

### Chunk

Chunking happens **within** a segment, never across one. A chunk spanning two
pages could not honestly cite either.

CSV chunks repeat the header row, because a chunk of bare values is unreadable
without its column names. The header comes out of the chunk budget rather than
being added on top of it, so repetition cannot push a chunk over its size.

### Embed

Chunks are embedded with the same `EmbeddingService` that memories use — one
provider for the whole system, so a chunk vector and a memory vector stay
comparable and a model change moves both. The vector lives on `file_chunks`
directly (768 dimensions, `nomic-embed-text`).

**A failure to embed marks the file `failed`, never `completed`.** A file
reported as ready but never embedded is invisible to every search the user
runs, and they discover it by asking a question and being told nothing was
found — which is indistinguishable from having uploaded nothing at all.

`indexed_at` records when embedding finished. It is the difference between
"chunked" and "searchable", and the UI shows that difference because the user
can act on it.

---

## Retrieval

Two retrievers run, because neither is sufficient alone.

**Vector search** finds passages that *mean* the same thing as the question,
and is the only way "what did I study?" reaches a chunk that says "coursework".
It is reliably bad at exact tokens — a surname, `BiLSTM`, a column header, a
version string — because an embedding smears those into a neighbourhood of
similar strings.

**Postgres full-text** is the mirror image: exact on terms, blind to paraphrase.

### Fusion

Results merge with **Reciprocal Rank Fusion** (`k = 60`), which combines *rank
positions* rather than scores. A cosine similarity and a `ts_rank` are not
comparable quantities, and normalising them against each other would invent a
relationship that does not exist. RRF only asks "how near the top did each
retriever put this?", which is a fair question to ask of both — and it means a
chunk found by *both* retrievers outranks one that merely came first in a
single list.

### The relevance gate

Top-N alone always returns N results. Asked "what is the capital of France?", a
library containing one resume returns that resume. The floor is what makes
"nothing here is relevant" an expressible outcome.

A **lexical-only hit is always kept** — it contains the literal words asked
about, which is evidence in its own right and precisely the case vector search
is worst at. A **semantic-only hit must clear the floor**, because "nearest of
everything I own" is not the same as "related to the question".

---

## Calibrating the floor

`FILE_RETRIEVAL_MIN_SIMILARITY = 0.50`, measured rather than inherited from the
memory system's floor. Different content, different distribution.

Reproduce with `python scripts/calibrate_retrieval_floor.py` (needs Ollama, and
`EMBEDDINGS_PROVIDER=ollama`).

**Method.** Three fixture documents on unrelated topics (a resume, an
architecture note, kitchen recipes) run through the real extraction and
chunking pipeline, embedded with `nomic-embed-text`. Three classes of pair:

- **relevant** — best similarity inside the document that answers the query
- **distractor** — best similarity in the *other* documents, same query
- **no-answer** — best similarity anywhere, for a query no document answers

**Results** (12 chunks, 12 grounded queries, 18 no-answer queries):

| class      |  n | min   | median | max   |
|------------|----|-------|--------|-------|
| relevant   | 12 | 0.480 | 0.613  | 0.752 |
| distractor | 12 | 0.403 | 0.451  | 0.494 |
| no-answer  | 18 | 0.369 | 0.430  | 0.505 |

| threshold | recall | precision | distractors kept | no-answer kept |
|-----------|--------|-----------|------------------|----------------|
| 0.45      | 1.00   | 0.52      | 6/12 | 5/18 |
| 0.47      | 1.00   | 0.75      | 3/12 | 1/18 |
| **0.50**  | **0.92** | **0.92** | **0/12** | **1/18** |
| 0.51      | 0.92   | 1.00      | 0/12 | 0/18 |
| 0.54      | 0.75   | 1.00      | 0/12 | 0/18 |

**The trade-off.** The distributions overlap: the weakest relevant pair scores
0.480 and the strongest no-answer query 0.505, so **no threshold is both
complete and precise.** 0.45 — the memory system's floor — would have kept a
third of the negatives, which is exactly why copying it would have been wrong.

0.50 rejects every cross-document distractor and 17 of 18 no-answer queries
while keeping 92% of relevant pairs. The single leak is *"what is the boiling
point of mercury"* matching *"Bake at 240C"* — a genuine temperature-to-
temperature semantic match, and an outlier (the next-highest no-answer query
scores 0.469). No similarity floor separates that from a 0.480 true positive.

0.51 is the F1 argmax, but a 30-pair fixture sample does not justify that last
decimal, and the difference between them is one fixture query.

**Limitation, stated plainly:** these are controlled fixtures, not a corpus of
real user documents, which did not exist at calibration time. The sample is
small. Re-run the script when the embedding model changes — a floor calibrated
for one model says nothing about another — and note that the statistics are
pinned in `tests/test_file_retrieval_calibration.py` so the constant cannot
drift away from its evidence unnoticed.

---

## Citations

Retrieval returns a `source_label` built from what extraction actually
recorded:

- `Resume.pdf — page 2`
- `Architecture.md — Agent Orchestration`
- `projects.csv — rows 2–26`
- `notes.txt` (no location available)

Chunk ids, chunk indices, scores and vectors stay out of the tool payload. They
are our bookkeeping, and a model handed them writes `[document_chunk_17]` at
the user.

---

## Performance

Measured with `python scripts/benchmark_rag.py` against local PostgreSQL 16 +
pgvector and Ollama (`nomic-embed-text`), on a 4.8 KB Markdown document
producing 30 chunks.

| stage | median | p95 |
|---|---|---|
| extraction (→ segments) | 0.1 ms | 0.2 ms |
| chunking (→ chunks) | 0.1 ms | 0.3 ms |
| embedding, per chunk | 106 ms | 358 ms |
| embedding, whole document | 4.0 s (30 chunks) | — |
| persist chunks + vectors | 320 ms (30 chunks) | — |
| query embedding, cold | 88 ms | 103 ms |
| query embedding, cached | 0.0 ms | 0.0 ms |
| hybrid search (SQL only) | 29 ms | 167 ms |
| hybrid search + embedding | 28 ms | 44 ms |
| full chat grounding | 52 ms | 77 ms |

Indexing is dominated entirely by embedding — a network round trip per chunk —
while extraction and chunking are effectively free. Retrieval is well inside a
conversational budget.

Two measurement traps the benchmark avoids, both of which produced meaningless
numbers on the first run: a fixture document that repeats itself yields
identical chunks the embedding cache answers instantly, and query embeddings
are cached, so cold and warm calls must be reported separately rather than
blended into one median that describes neither.

---

## Indexes

Both created in migration `0026_file_chunk_embeddings`:

```sql
CREATE INDEX ix_file_chunks_embedding
    ON file_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ix_file_chunks_content_fts
    ON file_chunks USING gin (to_tsvector('english', content));
```

The full-text query must spell `to_tsvector('english', content)` **exactly** as
the index does. Postgres only uses an expression index when the expressions
match character for character, so a differently-written cast still works while
silently sequential-scanning.

There is a related trap worth recording, because it shipped and was invisible:
binding the text-search configuration as a parameter renders
`to_tsvector($1::VARCHAR, content)`, and Postgres has **no such overload** —
only `to_tsvector(regconfig, text)`. Every full-text query raised. Nothing
appeared broken, because the unit suite runs on SQLite (which accepts it) and
document search degrades to keyword matching rather than failing loudly, so
hybrid retrieval ran on one leg. It was found by exercising the real Postgres
path during tenant-isolation testing. `tests/test_hybrid_retrieval_sql.py` now
compiles the statement against the Postgres dialect to catch that class of
defect without needing a live database.

---

## Tenancy

Every retrieval path filters on `user_id` **in the query itself**, in addition
to row-level security on `files` and `file_chunks`. Retrieval is the last place
to depend on a single layer: a policy accidentally dropped should still not
hand one user another's documents.

The application connects as `gummy_app`, which is `NOBYPASSRLS`.

Verified with two real users, two real documents and real embeddings, probing
every path a document can reach the model through — `hybrid_retrieval.search`,
`file_retrieval_service`, chat grounding, `file_search`, `file_list` and
`doc_read` (asked directly for the other user's file by name). None returned
the other tenant's content, and each user could still read their own.

---

## Degradation

Document search degrades rather than disappearing:

- **Embedding provider down** → the lexical half still runs; chunks containing
  the literal words are still found.
- **Hybrid retrieval unavailable** (no pgvector, SQLite tests) → falls back to
  ILIKE keyword matching, which finds strictly less but needs nothing but SQL.
- **Nothing relevant** → returns nothing, and the model says so rather than
  reaching for the nearest available document.

The fallback is silent to the caller by design — an outage in document search
must not take the conversation turn with it. That silence is also what hid the
`to_tsvector` defect above, which is why the dialect test exists.

---

## Files

| Path | Role |
|---|---|
| `services/files/extraction_service.py` | bytes → segments |
| `services/files/chunking_service.py` | segments → chunks |
| `services/files/indexing_service.py` | chunks → embeddings |
| `services/files/hybrid_retrieval.py` | vector + FTS + RRF + gate |
| `services/files/file_retrieval_service.py` | retrieval entry point |
| `services/files/file_context_service.py` | chat-turn grounding |
| `services/agents/tools/file_search.py` | `file_search`, `file_list` |
| `services/agents/tools/doc_read.py` | `doc_read` |
| `scripts/calibrate_retrieval_floor.py` | floor calibration |
| `scripts/benchmark_rag.py` | pipeline benchmark |
