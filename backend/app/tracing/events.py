"""Execution-trace events: the verifiable record of what every agent actually did."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.research import AgentName

TraceKind = Literal[
    "run_started",
    "run_finished",
    "agent_started",
    "agent_finished",
    "thought",  # an agent's reasoning summary
    "decision",  # an agent chose an action / next step
    "tool_call",
    "tool_result",
    "message",  # an AgentMessage was posted
    "adaptation",  # behaviour changed in response to circumstances (failover, refinement, …)
    "guard",  # a budget / termination guard fired
    "llm_call",
    "error",
]


class TraceEvent(BaseModel):
    run_id: str
    seq: int
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent: AgentName | Literal["system", "user"]
    kind: TraceKind
    summary: str = Field(description="One human-readable line")
    data: dict[str, Any] = Field(default_factory=dict)
