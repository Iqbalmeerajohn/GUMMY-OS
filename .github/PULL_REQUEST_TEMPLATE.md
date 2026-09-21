## What this changes

<!-- The behaviour difference, in a sentence or two. Not a restatement of the diff. -->

## Why

<!-- The reasoning and the trade-off. This is the part reviewers need and
     git log keeps. -->

## Verification

<!-- What you actually ran, and what it said. -->

```
cd backend  && uv run ruff check . && uv run black --check . && uv run mypy app && uv run pytest -q
cd frontend && npm run lint && npm run format:check && npx tsc --noEmit && npm test && npm run build
```

- [ ] Backend checks pass
- [ ] Frontend checks pass (if touched)
- [ ] New behaviour has a test, and it tests the failure case, not just the happy path

## If this touches tools, permissions or paths

- [ ] New tools are code-defined in `tools/catalog.py` with a tier
- [ ] Anything that changes state is Yellow or Red, not Green
- [ ] Host paths resolve through `tools/workspace.py`
- [ ] No agent ceiling was raised (or: it was, and here is why)

## What this does not do

<!-- Known gaps. A stated limitation is worth more than an implied promise. -->
