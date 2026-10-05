"""Export a run's trace for submission: JSONL (machine-readable) and Markdown (human-readable)."""

from collections import Counter
from pathlib import Path

from app.tracing.events import TraceEvent


def to_jsonl(events: list[TraceEvent]) -> str:
    return "".join(e.model_dump_json() + "\n" for e in events)


def write_jsonl(events: list[TraceEvent], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_jsonl(events), encoding="utf-8")
    return path


def to_markdown(events: list[TraceEvent]) -> str:
    if not events:
        return "# Execution trace\n\n_No events._\n"
    run_id = events[0].run_id
    kinds = Counter(e.kind for e in events)
    agents = Counter(e.agent for e in events if e.agent not in ("system", "user"))
    lines = [
        f"# Execution trace — run `{run_id}`",
        "",
        f"- Events: **{len(events)}**",
        f"- Agents active: {', '.join(f'{a} ({n})' for a, n in agents.most_common())}",
        f"- Messages: **{kinds['message']}** · Adaptations: **{kinds['adaptation']}** · "
        f"Tool calls: **{kinds['tool_call']}** · LLM calls: **{kinds['llm_call']}** · "
        f"Guards: **{kinds['guard']}** · Errors: **{kinds['error']}**",
        "",
        "| # | Time (UTC) | Agent | Kind | Summary |",
        "|---|---|---|---|---|",
    ]
    for e in events:
        summary = e.summary.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {e.seq} | {e.ts:%H:%M:%S} | {e.agent} | {e.kind} | {summary} |")
    return "\n".join(lines) + "\n"
