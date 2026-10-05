"""Research Planner: decomposes the question into sub-questions and sets evidence requirements."""

import json

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent, StateUpdate
from app.domain.research import ResearchPlan, SubQuestion
from app.graph.context import RunContext
from app.graph.state import ResearchState
from app.messaging import inbox

SYSTEM_PROMPT = """You are the Research Planner in a team of literature-review agents.
Decompose the user's research question into 2-5 focused, answerable sub-questions that together
cover it. For each, give 2-5 search keywords (synonyms and technical terms included).
If the user named a domain, tailor the sub-questions and vocabulary to that field. If not,
stay domain-general and centre the plan on the question's core concepts.
State concrete inclusion criteria and briefly justify the decomposition."""


class SubQuestionDraft(BaseModel):
    text: str
    keywords: list[str] = Field(min_length=1, max_length=6)


class PlanDraft(BaseModel):
    keywords: list[str] = Field(description="Core concepts and synonyms for the whole question")
    sub_questions: list[SubQuestionDraft] = Field(min_length=2, max_length=5)
    inclusion_criteria: list[str]
    rationale: str


class PlannerAgent(BaseAgent):
    name = "planner"
    system_prompt = SYSTEM_PROMPT

    async def act(self, state: ResearchState, ctx: RunContext) -> StateUpdate:
        request = state.request
        pending = inbox(state.messages, self.name, set(state.handled_message_ids))

        draft = await self.think(
            ctx,
            PlanDraft,
            json.dumps(
                {
                    "question": request.question,
                    "domain": request.domain,
                    "user_keywords": request.keywords,
                    "constraints": request.constraints.model_dump(),
                    "paper_budget": state.budget.max_papers,
                },
                indent=2,
            ),
            summary="Decomposed the research question into sub-questions",
        )

        min_papers = max(1, state.budget.max_papers // (2 * len(draft.sub_questions)))
        plan = ResearchPlan(
            domain_mode=f"domain:{request.domain}" if request.domain else "keyword",
            keywords=list(dict.fromkeys([*request.keywords, *draft.keywords])),
            sub_questions=[
                SubQuestion(id=f"SQ{i}", text=sq.text, keywords=sq.keywords, min_papers=min_papers)
                for i, sq in enumerate(draft.sub_questions, start=1)
            ],
            inclusion_criteria=draft.inclusion_criteria,
            rationale=draft.rationale,
        )
        self.decide(
            ctx,
            f"Plan v{plan.revision}: {len(plan.sub_questions)} sub-questions in "
            f"{plan.domain_mode} mode, ≥{min_papers} papers each",
            plan=plan,
        )
        request_search = self.send(
            ctx,
            "search",
            "REQUEST",
            "Find literature covering each sub-question of the plan",
            {"sub_question_ids": [sq.id for sq in plan.sub_questions]},
        )
        return {
            "plan": plan,
            "messages": [request_search],
            "handled_message_ids": [m.id for m in pending],
        }
