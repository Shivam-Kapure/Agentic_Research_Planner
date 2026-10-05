"""Collects trace events for one run and fans them out to sinks (SSE stream, DB, …)."""

import json
from collections.abc import Callable
from typing import Any

from app.llm.redaction import redact
from app.tracing.events import TraceEvent, TraceKind

TraceSink = Callable[[TraceEvent], None]

MAX_VALUE_CHARS = 2000


class TraceRecorder:
    def __init__(self, run_id: str, sinks: list[TraceSink] | None = None):
        self.run_id = run_id
        self.events: list[TraceEvent] = []
        self._sinks = list(sinks or [])

    def add_sink(self, sink: TraceSink) -> None:
        self._sinks.append(sink)

    def record(self, agent: str, kind: TraceKind, summary: str, **data: Any) -> TraceEvent:
        event = TraceEvent(
            run_id=self.run_id,
            seq=len(self.events) + 1,
            agent=agent,
            kind=kind,
            summary=redact(summary),
            data=_sanitise(data),
        )
        self.events.append(event)
        for sink in self._sinks:
            sink(event)
        return event

    def llm_event_sink(self, event: dict[str, Any]) -> None:
        """Adapter for LLMRouter.on_event: failovers become adaptation events."""
        agent = event.get("agent", "system")
        kind = event.get("kind")
        details = {k: v for k, v in event.items() if k not in ("agent", "kind")}
        target = f"{event['provider']}/{event['model']}"
        if kind == "llm_call":
            self.record(agent, "llm_call", f"LLM call to {target}", **details)
        elif kind == "llm_failure":
            self.record(agent, "error", f"LLM {target} failed", **details)
        elif kind == "llm_failover":
            previous = ", ".join(event.get("failed_over_from", []))
            self.record(agent, "adaptation", f"Failed over from {previous} to {target}", **details)

    def of_kind(self, kind: TraceKind) -> list[TraceEvent]:
        return [e for e in self.events if e.kind == kind]


def _sanitise(value: Any) -> Any:
    """Redact secrets and truncate very large values so traces stay small and safe."""
    if isinstance(value, dict):
        return {str(k): _sanitise(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_sanitise(v) for v in value]
    if hasattr(value, "model_dump"):
        return _sanitise(value.model_dump(mode="json"))
    if isinstance(value, str):
        text = redact(value)
        return text if len(text) <= MAX_VALUE_CHARS else text[:MAX_VALUE_CHARS] + "…[truncated]"
    if value is None or isinstance(value, bool | int | float):
        return value
    return _sanitise(json.loads(json.dumps(value, default=str)))
