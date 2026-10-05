"""Per-run runtime context: services and secrets that must NOT live in checkpointed state."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.llm import LLMRouter
from app.tracing import TraceRecorder

if TYPE_CHECKING:
    from app.tools.openalex import OpenAlexClient


@dataclass
class RunContext:
    run_id: str
    router: LLMRouter
    recorder: TraceRecorder
    openalex: "OpenAlexClient"
