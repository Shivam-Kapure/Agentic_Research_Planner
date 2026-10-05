"""The system's final output (published as the Output JSON Schema)."""

from typing import Literal

from pydantic import BaseModel

from app.domain.research import (
    Evidence,
    Paper,
    ResearchPlan,
    ResearchRequest,
    ReviewDraft,
    Synthesis,
)

RunStatus = Literal["running", "completed", "completed_with_limitations", "failed"]


class RunMetrics(BaseModel):
    agents_invoked: int
    agent_steps: int
    messages: int
    adaptations: int
    tool_calls: int
    llm_calls: int
    errors: int
    search_rounds: int
    replans: int
    duration_s: float


class ResearchOutput(BaseModel):
    run_id: str
    status: RunStatus
    request: ResearchRequest
    plan: ResearchPlan | None
    papers: list[Paper]
    evidence: list[Evidence]
    synthesis: Synthesis | None
    review: ReviewDraft | None
    bibliography: list[str]
    limitations: list[str]
    metrics: RunMetrics


def format_reference(paper: Paper) -> str:
    """Simple APA-style reference from OpenAlex metadata (refined with Crossref in S3)."""
    authors = paper.authors
    if not authors:
        who = "Unknown author"
    elif len(authors) <= 2:
        who = " & ".join(authors)
    else:
        who = f"{authors[0]} et al."
    year = paper.year or "n.d."
    venue = f" {paper.venue}." if paper.venue else ""
    doi = f" https://doi.org/{paper.doi}" if paper.doi else ""
    return f"{who} ({year}). {paper.title}.{venue}{doi}"
