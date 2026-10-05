"""Evidence Synthesis: compares evidence across studies, finds agreement, contradictions, gaps."""

import json

from app.agents.base import BaseAgent, StateUpdate
from app.domain.research import Synthesis
from app.graph.context import RunContext
from app.graph.state import ResearchState
from app.messaging import inbox

SYSTEM_PROMPT = """You are the Evidence Synthesis agent in a team of literature-review agents.
Compare the evidence items across studies for each sub-question:
- findings: what the evidence collectively supports, citing evidence ids, with strength
  (strong = several consistent studies, moderate = few or mixed-quality,
  weak = a single study or abstract-only evidence)
- contradictions: claims where evidence items disagree, listing ids on each side and a possible
  explanation (different populations, methods, metrics, time periods)
- research_gaps: what the evidence does not answer
Cite only evidence ids that exist. Do not add facts that are not in the evidence."""


class SynthesisAgent(BaseAgent):
    name = "synthesis"
    system_prompt = SYSTEM_PROMPT

    async def act(self, state: ResearchState, ctx: RunContext) -> StateUpdate:
        plan = state.plan
        if plan is None:
            raise ValueError("Synthesis requires a research plan")
        pending = inbox(state.messages, self.name, set(state.handled_message_ids))
        papers = {p.id: p for p in state.papers}

        synthesis = await self.think(
            ctx,
            Synthesis,
            json.dumps(
                {
                    "question": state.request.question,
                    "sub_questions": {sq.id: sq.text for sq in plan.sub_questions},
                    "evidence": [
                        {
                            "id": e.id,
                            "sub_question_id": e.sub_question_id,
                            "claim": e.claim,
                            "finding": e.finding,
                            "method": e.method,
                            "reliability": e.reliability,
                            "paper": f"{papers[e.paper_id].title} ({papers[e.paper_id].year})"
                            if e.paper_id in papers
                            else e.paper_id,
                        }
                        for e in state.evidence
                    ],
                },
                indent=2,
            ),
            summary=f"Compared {len(state.evidence)} evidence items across studies",
        )
        synthesis, dropped = drop_unknown_citations(synthesis, {e.id for e in state.evidence})
        if dropped:
            self.adapt(ctx, f"Removed {dropped} citations to non-existent evidence ids")

        self.decide(
            ctx,
            f"{len(synthesis.findings)} findings, {len(synthesis.contradictions)} contradictions, "
            f"{len(synthesis.research_gaps)} research gaps",
        )
        request_writer = self.send(
            ctx,
            "writer",
            "REQUEST",
            "Write the review from the synthesised findings",
            {"findings": len(synthesis.findings), "contradictions": len(synthesis.contradictions)},
        )
        return {
            "synthesis": synthesis,
            "messages": [request_writer],
            "handled_message_ids": [m.id for m in pending],
        }


def drop_unknown_citations(synthesis: Synthesis, known: set[str]) -> tuple[Synthesis, int]:
    """Keep only citations to evidence that exists; findings left with none are removed."""
    dropped = 0
    findings = []
    for finding in synthesis.findings:
        valid = [i for i in finding.evidence_ids if i in known]
        dropped += len(finding.evidence_ids) - len(valid)
        if valid:
            findings.append(finding.model_copy(update={"evidence_ids": valid}))
    contradictions = []
    for c in synthesis.contradictions:
        for_ids = [i for i in c.evidence_for if i in known]
        against_ids = [i for i in c.evidence_against if i in known]
        dropped += len(c.evidence_for) + len(c.evidence_against) - len(for_ids) - len(against_ids)
        if for_ids and against_ids:
            contradictions.append(
                c.model_copy(update={"evidence_for": for_ids, "evidence_against": against_ids})
            )
    cleaned = synthesis.model_copy(update={"findings": findings, "contradictions": contradictions})
    return cleaned, dropped
