"""Review Writer: drafts the review and verifies every claim cites real evidence."""

import json

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent, StateUpdate
from app.domain.research import Paragraph, ReviewDraft, ReviewSection
from app.graph.context import RunContext
from app.graph.state import ResearchState
from app.messaging import inbox

SYSTEM_PROMPT = """You are the Review Writer in a team of literature-review agents.
Write a structured academic literature review using ONLY the synthesised findings and evidence.
Sections: Introduction; one section per sub-question; Conflicting Evidence; Research Gaps;
Conclusion. Every paragraph outside the Introduction must list the evidence ids it relies on in
`citations` (e.g. ["E1", "E4"]). Do not state anything the evidence does not support."""

UNCITED_SECTIONS = {"introduction"}


class WriterOutput(BaseModel):
    title: str
    sections: list[ReviewSection] = Field(min_length=2)


class CitationReport(BaseModel):
    invalid_citations: int = 0
    unsupported_paragraphs: int = 0


class WriterAgent(BaseAgent):
    name = "writer"
    system_prompt = SYSTEM_PROMPT

    async def act(self, state: ResearchState, ctx: RunContext) -> StateUpdate:
        if state.synthesis is None or state.plan is None:
            raise ValueError("Writer requires a plan and a synthesis")
        pending = inbox(state.messages, self.name, set(state.handled_message_ids))

        output = await self.think(
            ctx,
            WriterOutput,
            json.dumps(
                {
                    "question": state.request.question,
                    "sub_questions": {sq.id: sq.text for sq in state.plan.sub_questions},
                    "synthesis": state.synthesis.model_dump(),
                    "evidence": [
                        {"id": e.id, "claim": e.claim, "finding": e.finding} for e in state.evidence
                    ],
                },
                indent=2,
            ),
            summary="Drafted the literature review",
        )
        draft, report = verify_citations(
            ReviewDraft(title=output.title, sections=output.sections),
            {e.id for e in state.evidence},
        )
        ctx.recorder.record(
            self.name,
            "tool_result",
            f"citation_verifier: {report.invalid_citations} invalid citations removed, "
            f"{report.unsupported_paragraphs} unsupported paragraphs",
            tool="citation_verifier",
            report=report,
        )
        approved = report.unsupported_paragraphs == 0
        draft.approved = approved
        self.decide(
            ctx,
            "Approved the review: every claim is backed by evidence"
            if approved
            else f"Review has {report.unsupported_paragraphs} unsupported paragraphs "
            "(revision loop arrives in S4)",
            report=report,
        )
        verdict = self.send(
            ctx,
            "planner",
            "APPROVAL" if approved else "REJECTION",
            "Review complete and citation-checked"
            if approved
            else "Review contains claims without supporting evidence",
            report.model_dump(),
        )
        return {
            "draft": draft,
            "messages": [verdict],
            "handled_message_ids": [m.id for m in pending],
            "limitations": []
            if approved
            else [f"{report.unsupported_paragraphs} review paragraphs lack evidence citations"],
        }


def verify_citations(draft: ReviewDraft, known: set[str]) -> tuple[ReviewDraft, CitationReport]:
    """Strip citations to unknown evidence and count body paragraphs left uncited."""
    report = CitationReport()
    sections = []
    for section in draft.sections:
        paragraphs = []
        for paragraph in section.paragraphs:
            valid = [c for c in dict.fromkeys(paragraph.citations) if c in known]
            report.invalid_citations += len(set(paragraph.citations)) - len(valid)
            if not valid and section.heading.strip().lower() not in UNCITED_SECTIONS:
                report.unsupported_paragraphs += 1
            paragraphs.append(Paragraph(text=paragraph.text, citations=valid))
        sections.append(ReviewSection(heading=section.heading, paragraphs=paragraphs))
    return draft.model_copy(update={"sections": sections}), report
