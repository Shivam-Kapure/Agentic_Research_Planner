import pytest
from pydantic import ValidationError

from app.domain.research import ResearchConstraints, ResearchRequest
from app.graph.state import budget_for


def test_valid_request_normalises_whitespace_keywords_and_domain():
    request = ResearchRequest(
        question="  Does   retrieval-augmented generation reduce hallucination?  ",
        domain="   ",
        keywords=["RAG", " RAG ", "", "hallucination"],
    )

    assert request.question == "Does retrieval-augmented generation reduce hallucination?"
    assert request.domain is None
    assert request.keywords == ["RAG", "hallucination"]
    assert request.require_plan_approval is True


@pytest.mark.parametrize(
    "question",
    ["", "short", "two words only here".replace(" only here", "")],
)
def test_rejects_empty_or_too_short_questions(question):
    with pytest.raises(ValidationError):
        ResearchRequest(question=question)


def test_rejects_inverted_or_future_year_ranges():
    with pytest.raises(ValidationError):
        ResearchConstraints(year_from=2024, year_to=2020)
    with pytest.raises(ValidationError):
        ResearchConstraints(year_to=3000)


def test_max_papers_is_bounded():
    with pytest.raises(ValidationError):
        ResearchConstraints(max_papers=500)


def test_budget_respects_depth_and_user_paper_cap():
    request = ResearchRequest(
        question="Is intermittent fasting better than calorie restriction?",
        depth="deep",
        constraints=ResearchConstraints(max_papers=8),
    )

    budget = budget_for(request)

    assert budget.max_papers == 8
    assert budget.max_search_rounds == 4
