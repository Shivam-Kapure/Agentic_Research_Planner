# Contributing to ResearchPilot

## One-time setup

1. Make sure `git config user.email` matches an email that is **verified on your GitHub account**. Otherwise your commits won't be attributed to you.
2. Clone the repo and create your branch from an up-to-date `main`.

## Branches

- `main` is protected and always deployable. No direct pushes.
- Branch names follow the pattern `<type>/<area>-<short-description>`, e.g. `feat/search-openalex-tool`, `fix/writer-citation-check`, `docs/design-diagram`, `test/planner-replan`.

## Daily workflow

1. `git switch main && git pull`
2. `git switch -c feat/<area>-<desc>`
3. Commit small, meaningful steps.
4. **Push your branch at the end of every working day**, even if the work is unfinished, and open a **draft PR** early.
5. When it's ready, mark the PR "Ready for review". It needs **1 approval + green CI** to merge.

## Commit messages (Conventional Commits)

```
<type>(<scope>): <imperative summary>

feat(search): add Semantic Scholar fallback when OpenAlex times out
fix(writer): drop claims without evidence IDs before approval
test(planner): cover replan after low-coverage report
docs(design): add orchestration pattern justification
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`, `perf`.
Scopes: `planner`, `search`, `analysis`, `synthesis`, `writer`, `graph`, `llm`, `trace`, `api`, `auth`, `keys`, `frontend`, `deploy`, `docs`.

## Reviews

Every PR is reviewed by the teammate responsible for that area (see `.github/CODEOWNERS`; GitHub requests them automatically):

| Area | Reviewer |
|---|---|
| Planner, orchestration, trace, LLM router | Kashyup (Shivam is the author) |
| Search, Analysis, tools, CI | Harsh |
| Synthesis, Writer, I/O schemas | Kashyup |
| Frontend, auth, keys, deployment | Kisna |

## Never commit

`.env`, API keys, Supabase secrets, `node_modules/`, virtual environments, local databases, or downloaded PDFs. If a secret is ever pushed, **revoke it immediately**. Deleting it in a later commit does not remove it from history.

## Integrity

Commit only your own work under your own login. The execution traces in `docs/traces/` must be exported from real runs and never edited by hand.
