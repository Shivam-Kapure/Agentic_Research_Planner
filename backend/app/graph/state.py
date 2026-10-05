"""The blackboard: shared research state every agent reads from and writes to.

It is checkpointed by LangGraph, so it must never hold secrets (API keys live in RunContext).
List fields annotated with `operator.add` are append-only: nodes return only new items.
"""

import operator
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.domain.research import (
    Depth,
    Evidence,
    Paper,
    ResearchPlan,
    ResearchRequest,
    ReviewDraft,
    Synthesis,
)
from app.messaging import AgentMessage

RunStatus = Literal["running", "completed", "completed_with_limitations", "failed"]


class Budget(BaseModel):
    """Hard limits enforced in code so agent loops always terminate."""

    max_papers: int
    max_search_rounds: int
    max_replans: int
    max_steps: int


DEPTH_BUDGETS: dict[Depth, Budget] = {
    "quick": Budget(max_papers=6, max_search_rounds=2, max_replans=1, max_steps=20),
    "standard": Budget(max_papers=12, max_search_rounds=3, max_replans=2, max_steps=35),
    "deep": Budget(max_papers=20, max_search_rounds=4, max_replans=2, max_steps=50),
}


def budget_for(request: ResearchRequest) -> Budget:
    base = DEPTH_BUDGETS[request.depth]
    return base.model_copy(
        update={"max_papers": min(base.max_papers, request.constraints.max_papers)}
    )


class ResearchState(BaseModel):
    run_id: str
    request: ResearchRequest
    budget: Budget

    plan: ResearchPlan | None = None
    papers: list[Paper] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    synthesis: Synthesis | None = None
    draft: ReviewDraft | None = None

    messages: Annotated[list[AgentMessage], operator.add] = Field(default_factory=list)
    handled_message_ids: Annotated[list[str], operator.add] = Field(default_factory=list)
    limitations: Annotated[list[str], operator.add] = Field(default_factory=list)

    steps: int = 0
    search_rounds: int = 0
    replans: int = 0
    status: RunStatus = "running"
