import httpx
import pytest
import respx

from app.tools.openalex import (
    OpenAlexClient,
    OpenAlexError,
    OpenAlexRateLimited,
    reconstruct_abstract,
)

WORK = {
    "id": "https://openalex.org/W4401042735",
    "doi": "https://doi.org/10.18653/v1/2024.naacl-industry.19",
    "title": "Reducing hallucination in structured outputs via Retrieval-Augmented Generation",
    "publication_year": 2024,
    "cited_by_count": 95,
    "abstract_inverted_index": {"RAG": [0], "reduces": [1], "hallucination.": [2]},
    "authorships": [{"author": {"display_name": "Orlando Ayala"}}],
    "primary_location": {"source": {"display_name": "NAACL"}},
    "best_oa_location": {"pdf_url": "https://aclanthology.org/2024.naacl-industry.19.pdf"},
}


def test_reconstruct_abstract_orders_words_by_position():
    assert reconstruct_abstract({"world": [1], "hello": [0], "again": [2]}) == "hello world again"
    assert reconstruct_abstract(None) is None


@respx.mock
async def test_search_maps_works_and_reports_remaining_credits():
    route = respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(
            200,
            json={"meta": {"count": 35377}, "results": [WORK, {"id": "W0", "title": None}]},
            headers={"X-RateLimit-Remaining": "990"},
        )
    )
    client = OpenAlexClient(mailto="team@example.com")

    result = await client.search_works(
        "rag hallucination", per_page=5, year_from=2020, year_to=2025, include_preprints=False
    )

    params = route.calls.last.request.url.params
    assert params["search"] == "rag hallucination"
    assert params["filter"] == (
        "has_abstract:true,from_publication_date:2020-01-01,"
        "to_publication_date:2025-12-31,type:!preprint"
    )
    assert params["mailto"] == "team@example.com"
    assert result.total_count == 35377
    assert result.credits_remaining == 990
    [paper] = result.papers
    assert paper.id == "W4401042735"
    assert paper.doi == "10.18653/v1/2024.naacl-industry.19"
    assert paper.abstract == "RAG reduces hallucination."
    assert paper.venue == "NAACL"
    assert paper.oa_pdf_url.endswith(".pdf")


@respx.mock
async def test_rate_limit_and_server_errors_raise_typed_errors():
    respx.get("https://api.openalex.org/works").mock(
        side_effect=[httpx.Response(429), httpx.Response(503), httpx.ConnectError("down")]
    )
    client = OpenAlexClient()

    with pytest.raises(OpenAlexRateLimited):
        await client.search_works("q")
    with pytest.raises(OpenAlexError, match="503"):
        await client.search_works("q")
    with pytest.raises(OpenAlexError, match="ConnectError"):
        await client.search_works("q")
