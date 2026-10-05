# Backend

This is the FastAPI + LangGraph service that hosts the five ResearchPilot agents. The planned layout is in [`../docs/IMPLEMENTATION_PLAN.md`](../docs/IMPLEMENTATION_PLAN.md) §5.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync                      # create .venv and install dependencies
cp ../.env.example ../.env   # then fill in values (never commit .env)
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

The API runs at http://localhost:8000, and interactive docs are at http://localhost:8000/docs.

## Test and lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
