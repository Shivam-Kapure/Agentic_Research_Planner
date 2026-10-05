"""Core research domain models: the system's input, the shared research artefacts on the
blackboard, and the final output. These double as the published I/O JSON Schemas.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

AgentName = Literal["planner", "search", "analysis", "synthesis", "writer"]
AGENT_NAMES: tuple[AgentName, ...] = ("planner", "search", "analysis", "synthesis", "writer")

Depth = Literal["quick", "standard", "deep"]
Reliability = Literal["full_text", "abstract_only"]
Strength = Literal["strong", "moderate", "weak"]


# ---------------------------------------------------------------- input


class ResearchConstraints(BaseModel):
    year_from: int | None = Field(default=None, ge=1900)
    year_to: int | None = Field(default=None, ge=1900)
    max_papers: int = Field(default=12, ge=3, le=30)
    include_preprints: bool = True

    @model_validator(mode="after")
    def _check_years(self) -> "ResearchConstraints":
        current = date.today().year
        if self.year_to is not None and self.year_to > current:
            raise ValueError(f"year_to cannot be later than {current}")
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("year_from must not be after year_to")
        return self


class ResearchRequest(BaseModel):
    """What a user submits to start a literature review."""

    question: str = Field(min_length=15, max_length=500)
    domain: str | None = Field(
        default=None, max_length=80, description="Optional field; null → keyword mode"
    )
    keywords: list[str] = Field(default_factory=list, max_length=10)
    constraints: ResearchConstraints = Field(default_factory=ResearchConstraints)
    depth: Depth = "standard"
    require_plan_approval: bool = True

    @field_validator("question")
    @classmethod
    def _question_has_words(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value.split()) < 3:
            raise ValueError("question must contain at least three words")
        return value

    @field_validator("domain")
    @classmethod
    def _blank_domain_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @field_validator("keywords")
    @classmethod
    def _clean_keywords(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(k.strip() for k in value if k.strip()))


# ---------------------------------------------------------------- blackboard artefacts


class SubQuestion(BaseModel):
    id: str = Field(description="Stable id such as 'SQ1'")
    text: str
    keywords: list[str] = Field(default_factory=list)
    min_papers: int = Field(default=2, ge=1)


class ResearchPlan(BaseModel):
    domain_mode: str = Field(description="'keyword' or 'domain:<name>'")
    keywords: list[str]
    sub_questions: list[SubQuestion] = Field(min_length=1)
    inclusion_criteria: list[str] = Field(default_factory=list)
    rationale: str = ""
    revision: int = 0


class Paper(BaseModel):
    id: str = Field(description="Source id, e.g. OpenAlex 'W4401042735'")
    title: str
    year: int | None = None
    doi: str | None = None
    authors: list[str] = Field(default_factory=list)
    venue: str | None = None
    abstract: str | None = None
    cited_by_count: int = 0
    oa_pdf_url: str | None = None
    source: str = "openalex"
    sub_question_ids: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    id: str = Field(description="Stable id such as 'E3'")
    paper_id: str
    sub_question_id: str
    claim: str
    method: str | None = None
    finding: str | None = None
    limitations: str | None = None
    reliability: Reliability = "abstract_only"
    confidence: float = Field(default=0.5, ge=0, le=1)


class Finding(BaseModel):
    sub_question_id: str
    statement: str
    evidence_ids: list[str]
    strength: Strength


class Contradiction(BaseModel):
    claim: str
    evidence_for: list[str]
    evidence_against: list[str]
    status: Literal["open", "explained", "resolved"] = "open"
    explanation: str | None = None


class Synthesis(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    research_gaps: list[str] = Field(default_factory=list)


class Paragraph(BaseModel):
    text: str
    citations: list[str] = Field(default_factory=list, description="Evidence ids")


class ReviewSection(BaseModel):
    heading: str
    paragraphs: list[Paragraph]


class ReviewDraft(BaseModel):
    title: str
    sections: list[ReviewSection]
    approved: bool = False
