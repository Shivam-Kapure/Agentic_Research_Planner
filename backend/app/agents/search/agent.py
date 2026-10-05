"""Literature Search: turns sub-questions into queries, searches, dedupes and checks coverage."""

import asyncio
import json
import math

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent, StateUpdate
from app.domain.research import Paper, ResearchPlan
from app.graph.context import RunContext
from app.graph.state import ResearchState
from app.messaging import inbox
from app.tools.openalex import OpenAlexError, SearchResult

SYSTEM_PROMPT = """You are the Literature Search agent in a team of literature-review agents.
For each sub-question write ONE concise scholarly search query (3-7 words) for the OpenAlex
search engine: use the key technical terms, no boolean operators, no quotes, no filler words.
Explain your query choices in one or two sentences."""


class QueryDraft(BaseModel):
    sub_question_id: str
    query: str


class SearchStrategy(BaseModel):
    queries: list[QueryDraft] = Field(min_length=1)
    reasoning: str


class SearchAgent(BaseAgent):
    name = "search"
    system_prompt = SYSTEM_PROMPT

    async def act(self, state: ResearchState, ctx: RunContext) -> StateUpdate:
        plan = state.plan
        if plan is None:
            raise ValueError("Search requires a research plan")
        pending = inbox(state.messages, self.name, set(state.handled_message_ids))

        strategy = await self.think(
            ctx,
            SearchStrategy,
            json.dumps(
                {
                    "question": state.request.question,
                    "domain_mode": plan.domain_mode,
                    "sub_questions": [sq.model_dump() for sq in plan.sub_questions],
                },
                indent=2,
            ),
            summary="Designed one search query per sub-question",
        )
        queries = self._complete_queries(ctx, plan, strategy)

        per_query = math.ceil(state.budget.max_papers / len(plan.sub_questions)) + 3
        constraints = state.request.constraints
        results = await asyncio.gather(
            *(
                self._search(ctx, sq_id, query, per_query, constraints)
                for sq_id, query in queries.items()
            )
        )
        by_sq = {sq_id: result.papers for sq_id, result in results if result}
        papers = select_papers(by_sq, state.budget.max_papers)

        coverage = {
            sq.id: sum(sq.id in p.sub_question_ids for p in papers) for sq in plan.sub_questions
        }
        thin = [sq.id for sq in plan.sub_questions if coverage[sq.id] < sq.min_papers]
        self.decide(
            ctx,
            f"Selected {len(papers)} papers; coverage {coverage}"
            + (f"; below target for {', '.join(thin)}" if thin else "; all sub-questions covered"),
            coverage=coverage,
            thin_sub_questions=thin,
        )
        request_analysis = self.send(
            ctx,
            "analysis",
            "REQUEST",
            f"Extract evidence from {len(papers)} selected papers",
            {"paper_ids": [p.id for p in papers]},
        )
        return {
            "papers": papers,
            "search_rounds": state.search_rounds + 1,
            "messages": [request_analysis],
            "handled_message_ids": [m.id for m in pending],
            "limitations": [f"Low literature coverage for {sq}" for sq in thin],
        }

    def _complete_queries(
        self, ctx: RunContext, plan: ResearchPlan, strategy: SearchStrategy
    ) -> dict[str, str]:
        """Keep valid queries; fall back to keyword queries for any sub-question the LLM missed."""
        queries = {
            q.sub_question_id: q.query.strip()
            for q in strategy.queries
            if q.query.strip() and q.sub_question_id in {sq.id for sq in plan.sub_questions}
        }
        for sq in plan.sub_questions:
            if sq.id not in queries:
                queries[sq.id] = " ".join(sq.keywords[:4])
                self.adapt(ctx, f"No query proposed for {sq.id}; using its keywords instead")
        return queries

    async def _search(self, ctx, sq_id, query, per_page, constraints):
        try:
            result: SearchResult = await self.use_tool(
                ctx,
                "openalex_search",
                lambda: ctx.openalex.search_works(
                    query,
                    per_page=per_page,
                    year_from=constraints.year_from,
                    year_to=constraints.year_to,
                    include_preprints=constraints.include_preprints,
                ),
                args={"sub_question": sq_id, "query": query},
                describe=lambda r: (
                    f"{len(r.papers)} papers for {sq_id} ({r.total_count} total matches"
                    + (f", {r.credits_remaining} credits left)" if r.credits_remaining else ")")
                ),
            )
        except OpenAlexError:
            return sq_id, None
        return sq_id, result


def select_papers(by_sq: dict[str, list[Paper]], limit: int) -> list[Paper]:
    """Round-robin across sub-questions (keeping each list's relevance order) and dedupe,
    so every sub-question gets a fair share of the paper budget."""
    selected: dict[str, Paper] = {}
    queues = {sq: list(papers) for sq, papers in by_sq.items()}
    while len(selected) < limit and any(queues.values()):
        for sq_id, queue in queues.items():
            while queue:
                paper = queue.pop(0)
                if paper.id in selected:
                    if sq_id not in selected[paper.id].sub_question_ids:
                        selected[paper.id].sub_question_ids.append(sq_id)
                    continue
                if len(selected) < limit:
                    selected[paper.id] = paper.model_copy(update={"sub_question_ids": [sq_id]})
                break
    return list(selected.values())
