"""Command-line runner for development and for capturing real execution traces.

    uv run python -m app.cli "Does retrieval-augmented generation reduce hallucination?" \
        --depth quick --max-papers 6

Uses DEV_GROQ_API_KEY / DEV_GEMINI_API_KEY from .env (production uses per-user keys).
Writes output.json, trace.jsonl and trace.md to runs/<run_id>/.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from pydantic import SecretStr, ValidationError

from app.config import get_settings
from app.domain.research import ResearchConstraints, ResearchRequest
from app.graph.runner import run_research
from app.llm import LLMCredentials
from app.tracing import TraceEvent
from app.tracing.exporters import to_markdown, write_jsonl


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a ResearchPilot literature review")
    parser.add_argument("question")
    parser.add_argument("--domain", default=None)
    parser.add_argument("--keywords", nargs="*", default=[])
    parser.add_argument("--depth", choices=["quick", "standard", "deep"], default="quick")
    parser.add_argument("--max-papers", type=int, default=6)
    parser.add_argument("--year-from", type=int, default=None)
    parser.add_argument("--year-to", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("runs"))
    return parser.parse_args(argv)


def print_event(event: TraceEvent) -> None:
    if event.kind in {"llm_call", "agent_finished"}:
        return
    print(f"[{event.seq:>3}] {event.agent:<9} {event.kind:<13} {event.summary}", flush=True)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    try:
        request = ResearchRequest(
            question=args.question,
            domain=args.domain,
            keywords=args.keywords,
            depth=args.depth,
            require_plan_approval=False,
            constraints=ResearchConstraints(
                max_papers=args.max_papers, year_from=args.year_from, year_to=args.year_to
            ),
        )
    except ValidationError as exc:
        print(f"Invalid request:\n{exc}", file=sys.stderr)
        return 2

    credentials = LLMCredentials(
        groq_api_key=SecretStr(settings.dev_groq_api_key) if settings.dev_groq_api_key else None,
        gemini_api_key=SecretStr(settings.dev_gemini_api_key)
        if settings.dev_gemini_api_key
        else None,
    )
    if not credentials.available_providers:
        print("Set DEV_GROQ_API_KEY and/or DEV_GEMINI_API_KEY in .env", file=sys.stderr)
        return 2

    outcome = await run_research(request, credentials, settings, sinks=[print_event])

    run_dir = args.out / outcome.output.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "output.json").write_text(outcome.output.model_dump_json(indent=2), "utf-8")
    write_jsonl(outcome.events, run_dir / "trace.jsonl")
    (run_dir / "trace.md").write_text(to_markdown(outcome.events), "utf-8")

    metrics = outcome.output.metrics
    print(
        f"\nStatus: {outcome.output.status} | papers {len(outcome.output.papers)} | "
        f"evidence {len(outcome.output.evidence)} | messages {metrics.messages} | "
        f"adaptations {metrics.adaptations} | {metrics.duration_s}s\nSaved to {run_dir}"
    )
    return 0 if outcome.output.status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
