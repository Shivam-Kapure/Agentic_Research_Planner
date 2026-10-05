"""End-to-end run of all five agents with a fake LLM and mocked OpenAlex (no network)."""

import httpx
import pytest
import respx
from pydantic import SecretStr

from app.agents.analysis.agent import EvidenceDraft, PaperAnalysis
from app.agents.planner.agent import PlanDraft, SubQuestionDraft
from app.agents.search.agent import QueryDraft, SearchStrategy
from app.agents.writer.agent import WriterOutput
from app.config import Settings
from app.domain.research import (
    Finding,
    Paragraph,
    ResearchRequest,
    ReviewSection,
    Synthesis,
)
from app.graph.runner import run_research
from app.llm import LLMCredentials
from tests.fakes import SchemaFakeModel, factory_for

GROQ_KEY = "gsk_" + "T" * 24
CREDENTIALS = LLMCredentials(SecretStr(GROQ_KEY), SecretStr("AIza" + "G" * 35))
SETTINGS = Settings(_env_file=None, app_env="test")
REQUEST = ResearchRequest(
    question="Does retrieval-augmented generation reduce hallucination in LLMs?",
    depth="quick",
    require_plan_approval=False,
)


def work(i: int, title: str) -> dict:
    return {
        "id": f"https://openalex.org/W{i}",
        "title": title,
        "publication_year": 2020 + i,
        "cited_by_count": 10 * i,
        "abstract_inverted_index": {"RAG": [0], "helps": [1], f"study{i}": [2]},
        "authorships": [{"author": {"display_name": f"Author {i}"}}],
    }


WORKS = [work(1, "Alpha: RAG grounding"), work(2, "Beta: fine-tuning"), work(3, "Alpha: eval")]


def happy_responder(schema, messages):
    prompt = messages[-1].content
    if schema is PlanDraft:
        return PlanDraft(
            keywords=["retrieval-augmented generation", "hallucination"],
            sub_questions=[
                SubQuestionDraft(text="Does RAG reduce hallucination?", keywords=["RAG"]),
                SubQuestionDraft(
                    text="How does it compare to fine-tuning?", keywords=["fine-tuning"]
                ),
            ],
            inclusion_criteria=["empirical studies"],
            rationale="Effect, then comparison.",
        )
    if schema is SearchStrategy:  # deliberately omits SQ2 → agent must adapt
        return SearchStrategy(
            queries=[QueryDraft(sub_question_id="SQ1", query="RAG hallucination")],
            reasoning="Core terms.",
        )
    if schema is PaperAnalysis:
        sq = "SQ1" if "Alpha" in prompt else "SQ2"
        return PaperAnalysis(
            relevant=True,
            evidence=[EvidenceDraft(sub_question_id=sq, claim=f"claim for {sq}", confidence=0.6)],
        )
    if schema is Synthesis:
        return Synthesis(
            findings=[
                Finding(
                    sub_question_id="SQ1",
                    statement="RAG helps",
                    evidence_ids=["E1", "E99"],
                    strength="moderate",
                )
            ],
            research_gaps=["Few long-term studies"],
        )
    if schema is WriterOutput:
        return WriterOutput(
            title="RAG and hallucination",
            sections=[
                ReviewSection(heading="Introduction", paragraphs=[Paragraph(text="Context.")]),
                ReviewSection(
                    heading="SQ1", paragraphs=[Paragraph(text="RAG helps.", citations=["E1"])]
                ),
            ],
        )
    raise AssertionError(f"unexpected schema {schema}")


def mock_openalex(response: httpx.Response | None = None):
    return respx.get("https://api.openalex.org/works").mock(
        return_value=response or httpx.Response(200, json={"meta": {"count": 3}, "results": WORKS})
    )


async def run(responders: dict):
    models = {provider: SchemaFakeModel(r) for provider, r in responders.items()}
    return await run_research(REQUEST, CREDENTIALS, SETTINGS, model_factory=factory_for(models))


@respx.mock
async def test_all_five_agents_collaborate_end_to_end():
    mock_openalex()

    outcome = await run({"groq": happy_responder, "gemini": happy_responder})
    output, events = outcome.output, outcome.events

    assert output.status == "completed"
    assert output.metrics.agents_invoked == 5
    assert len(output.plan.sub_questions) == 2
    assert {p.id for p in output.papers} == {"W1", "W2", "W3"}
    assert len(output.evidence) == 3 and output.review.approved
    assert len(output.bibliography) == 3

    hops = [
        (e.data["message"]["sender"], e.data["message"]["recipient"])
        for e in events
        if e.kind == "message"
    ]
    assert hops == [
        ("planner", "search"),
        ("search", "analysis"),
        ("analysis", "synthesis"),
        ("synthesis", "writer"),
        ("writer", "planner"),
    ]
    adaptations = [e.summary for e in events if e.kind == "adaptation"]
    assert any("SQ2" in s for s in adaptations)  # missing query → keyword fallback
    assert any("non-existent evidence" in s for s in adaptations)  # E99 dropped
    assert GROQ_KEY not in "".join(e.model_dump_json() for e in events)


@respx.mock
async def test_provider_failure_fails_over_and_is_traced():
    mock_openalex()

    def groq_down(schema, messages):
        return RuntimeError("503 groq unavailable")

    outcome = await run({"groq": groq_down, "gemini": happy_responder})

    assert outcome.output.status == "completed"
    failovers = [e for e in outcome.events if e.kind == "adaptation" and "Failed over" in e.summary]
    assert {e.agent for e in failovers} >= {"planner", "search", "synthesis"}


@respx.mock
async def test_search_outage_degrades_gracefully_instead_of_crashing():
    mock_openalex(httpx.Response(503))

    outcome = await run({"groq": happy_responder, "gemini": happy_responder})
    output = outcome.output

    assert output.papers == [] and output.evidence == []
    assert output.status == "completed_with_limitations"
    assert any("Low literature coverage" in lim for lim in output.limitations)
    assert any(e.kind == "error" and "openalex_search" in e.summary for e in outcome.events)


@pytest.mark.parametrize("bad", ["", "too short"])
def test_invalid_questions_are_rejected_before_any_agent_runs(bad):
    with pytest.raises(ValueError):
        ResearchRequest(question=bad)
