"""Document Analysis: extracts structured, reliability-rated evidence from each paper."""

import asyncio
import json

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent, StateUpdate
from app.domain.research import Evidence, Paper
from app.graph.context import RunContext
from app.graph.state import ResearchState
from app.messaging import inbox

SYSTEM_PROMPT = """You are the Document Analysis agent in a team of literature-review agents.
Read the paper and extract only evidence that is actually stated in the text. For each relevant
sub-question give: the paper's claim, its method/design, the concrete finding (numbers if
given), and stated limitations. Rate your confidence 0-1, lower when the text is only an
abstract or vague. If the paper is not relevant, say so and return no evidence. Never invent."""

MAX_CONCURRENT = 3


class EvidenceDraft(BaseModel):
    sub_question_id: str
    claim: str
    method: str | None = None
    finding: str | None = None
    limitations: str | None = None
    confidence: float = Field(ge=0, le=1)


class PaperAnalysis(BaseModel):
    relevant: bool
    evidence: list[EvidenceDraft] = Field(default_factory=list, max_length=3)


class AnalysisAgent(BaseAgent):
    name = "analysis"
    system_prompt = SYSTEM_PROMPT

    async def act(self, state: ResearchState, ctx: RunContext) -> StateUpdate:
        plan = state.plan
        if plan is None:
            raise ValueError("Analysis requires a research plan")
        pending = inbox(state.messages, self.name, set(state.handled_message_ids))
        sub_questions = {sq.id: sq.text for sq in plan.sub_questions}

        readable = [p for p in state.papers if p.abstract]
        if skipped := len(state.papers) - len(readable):
            self.adapt(ctx, f"Skipping {skipped} papers with no available text")
        self.decide(ctx, f"Analysing {len(readable)} papers from their abstracts (PDF in S3)")

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        async def analyse(paper: Paper) -> tuple[Paper, PaperAnalysis | None]:
            async with semaphore:
                try:
                    return paper, await self.think(
                        ctx,
                        PaperAnalysis,
                        _paper_prompt(paper, sub_questions),
                        summary=f"Analysed {paper.id}: {paper.title[:70]}",
                    )
                except Exception as exc:  # one bad paper must not sink the whole analysis
                    ctx.recorder.record(self.name, "error", f"Could not analyse {paper.id}: {exc}")
                    return paper, None

        analyses = await asyncio.gather(*(analyse(p) for p in readable))

        evidence: list[Evidence] = []
        failed = 0
        for paper, analysis in analyses:
            if analysis is None:
                failed += 1
                continue
            for item in analysis.evidence if analysis.relevant else []:
                if item.sub_question_id not in sub_questions:
                    continue
                evidence.append(
                    Evidence(
                        id=f"E{len(evidence) + 1}",
                        paper_id=paper.id,
                        reliability="abstract_only",
                        **item.model_dump(),
                    )
                )
        irrelevant = sum(1 for _, a in analyses if a is not None and not a.relevant)
        self.decide(
            ctx,
            f"Extracted {len(evidence)} evidence items; {irrelevant} papers judged irrelevant"
            + (f"; {failed} failed" if failed else ""),
        )
        request_synthesis = self.send(
            ctx,
            "synthesis",
            "REQUEST",
            f"Synthesise {len(evidence)} evidence items across sub-questions",
            {"evidence_ids": [e.id for e in evidence]},
        )
        return {
            "evidence": evidence,
            "messages": [request_synthesis],
            "handled_message_ids": [m.id for m in pending],
            "limitations": [f"{failed} papers could not be analysed"] if failed else [],
        }


def _paper_prompt(paper: Paper, sub_questions: dict[str, str]) -> str:
    return json.dumps(
        {
            "sub_questions": sub_questions,
            "paper": {
                "title": paper.title,
                "year": paper.year,
                "venue": paper.venue,
                "text_type": "abstract",
                "text": paper.abstract,
            },
        },
        indent=2,
    )
