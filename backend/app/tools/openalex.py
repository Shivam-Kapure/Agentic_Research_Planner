"""OpenAlex works search (https://api.openalex.org).

OpenAlex meters usage in credits (a search costs ~10 of 1,000 free daily credits without a
key), so the client surfaces the remaining budget for agents to reason about.
"""

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.domain.research import Paper

BASE_URL = "https://api.openalex.org"
_SELECT = ",".join(
    [
        "id",
        "doi",
        "title",
        "publication_year",
        "cited_by_count",
        "abstract_inverted_index",
        "authorships",
        "primary_location",
        "best_oa_location",
        "type",
    ]
)


class OpenAlexError(RuntimeError):
    pass


class OpenAlexRateLimited(OpenAlexError):
    pass


@dataclass
class SearchResult:
    query: str
    total_count: int
    papers: list[Paper] = field(default_factory=list)
    credits_remaining: int | None = None


class OpenAlexClient:
    def __init__(
        self,
        mailto: str = "",
        api_key: str = "",
        http: httpx.AsyncClient | None = None,
        timeout: float = 20.0,
    ):
        self._mailto = mailto
        self._api_key = api_key
        self._http = http or httpx.AsyncClient(base_url=BASE_URL, timeout=timeout)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def search_works(
        self,
        query: str,
        *,
        per_page: int = 8,
        year_from: int | None = None,
        year_to: int | None = None,
        include_preprints: bool = True,
    ) -> SearchResult:
        filters = ["has_abstract:true"]
        if year_from:
            filters.append(f"from_publication_date:{year_from}-01-01")
        if year_to:
            filters.append(f"to_publication_date:{year_to}-12-31")
        if not include_preprints:
            filters.append("type:!preprint")
        params: dict[str, Any] = {
            "search": query,
            "filter": ",".join(filters),
            "per_page": max(1, min(per_page, 50)),
            "select": _SELECT,
        }
        if self._mailto:
            params["mailto"] = self._mailto
        if self._api_key:
            params["api_key"] = self._api_key

        try:
            response = await self._http.get(f"{BASE_URL}/works", params=params)
        except httpx.HTTPError as exc:
            raise OpenAlexError(f"OpenAlex request failed: {type(exc).__name__}") from exc
        if response.status_code == 429:
            raise OpenAlexRateLimited("OpenAlex rate limit / daily credit budget exhausted")
        if response.status_code >= 400:
            raise OpenAlexError(f"OpenAlex returned HTTP {response.status_code}")

        body = response.json()
        remaining = response.headers.get("x-ratelimit-remaining")
        return SearchResult(
            query=query,
            total_count=int(body.get("meta", {}).get("count") or 0),
            papers=[_to_paper(w) for w in body.get("results", []) if w.get("title")],
            credits_remaining=int(remaining) if remaining and remaining.isdigit() else None,
        )


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex stores abstracts as {word: [positions]}; rebuild the plain text."""
    if not inverted_index:
        return None
    positions = [(pos, word) for word, poses in inverted_index.items() for pos in poses]
    return " ".join(word for _, word in sorted(positions)) or None


def _strip_prefix(value: str | None, prefix: str) -> str | None:
    if not value:
        return None
    return value.removeprefix(prefix)


def _to_paper(work: dict[str, Any]) -> Paper:
    primary = work.get("primary_location") or {}
    best_oa = work.get("best_oa_location") or {}
    return Paper(
        id=_strip_prefix(work.get("id"), "https://openalex.org/") or "",
        title=work["title"],
        year=work.get("publication_year"),
        doi=_strip_prefix(work.get("doi"), "https://doi.org/"),
        authors=[
            a["author"]["display_name"]
            for a in (work.get("authorships") or [])[:6]
            if a.get("author", {}).get("display_name")
        ],
        venue=(primary.get("source") or {}).get("display_name"),
        abstract=reconstruct_abstract(work.get("abstract_inverted_index")),
        cited_by_count=work.get("cited_by_count") or 0,
        oa_pdf_url=best_oa.get("pdf_url"),
        source="openalex",
    )
