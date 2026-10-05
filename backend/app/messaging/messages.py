"""Typed inter-agent messages. Agents coordinate by posting these to the blackboard."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.domain.research import AgentName

MessageType = Literal[
    "REQUEST",  # ask another agent to do something
    "RESPONSE",  # answer to a REQUEST
    "CRITIQUE",  # challenge another agent's output
    "CONFLICT",  # two agents disagree; needs arbitration
    "REPLAN_REQUEST",  # ask the planner to revise the plan
    "RESOLUTION",  # planner's arbitration outcome
    "APPROVAL",
    "REJECTION",
    "HUMAN_FEEDBACK",  # user feedback on the plan, relayed to the planner
]


def _new_id() -> str:
    return f"msg_{uuid4().hex[:10]}"


class AgentMessage(BaseModel):
    id: str = Field(default_factory=_new_id)
    sender: AgentName | Literal["user", "system"]
    recipient: AgentName
    type: MessageType
    reason: str = Field(description="Why the sender is sending this (LLM-generated)")
    payload: dict[str, Any] = Field(default_factory=dict)
    in_reply_to: str | None = None
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))


def inbox(messages: list[AgentMessage], agent: AgentName, handled: set[str]) -> list[AgentMessage]:
    """Messages addressed to `agent` that it has not handled yet, oldest first."""
    return [m for m in messages if m.recipient == agent and m.id not in handled]
