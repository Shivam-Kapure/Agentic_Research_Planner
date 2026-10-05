from app.agents.search.agent import select_papers
from app.agents.synthesis.agent import drop_unknown_citations
from app.agents.writer.agent import verify_citations
from app.domain.output import format_reference
from app.domain.research import (
    Contradiction,
    Finding,
    Paper,
    Paragraph,
    ReviewDraft,
    ReviewSection,
    Synthesis,
)


def paper(pid: str, **kw) -> Paper:
    return Paper(id=pid, title=f"Paper {pid}", **kw)


def test_select_papers_round_robins_across_sub_questions_and_dedupes():
    by_sq = {
        "SQ1": [paper("A"), paper("B"), paper("C")],
        "SQ2": [paper("A"), paper("D")],
    }

    selected = select_papers(by_sq, limit=3)

    assert [p.id for p in selected] == ["A", "D", "B"]
    shared = next(p for p in selected if p.id == "A")
    assert shared.sub_question_ids == ["SQ1", "SQ2"]


def test_select_papers_respects_limit_and_empty_input():
    assert len(select_papers({"SQ1": [paper(str(i)) for i in range(10)]}, limit=4)) == 4
    assert select_papers({}, limit=4) == []


def test_drop_unknown_citations_removes_bad_ids_and_empty_items():
    synthesis = Synthesis(
        findings=[
            Finding(
                sub_question_id="SQ1",
                statement="ok",
                evidence_ids=["E1", "E9"],
                strength="moderate",
            ),
            Finding(sub_question_id="SQ1", statement="bogus", evidence_ids=["E9"], strength="weak"),
        ],
        contradictions=[
            Contradiction(claim="c", evidence_for=["E1"], evidence_against=["E2"]),
            Contradiction(claim="one-sided", evidence_for=["E1"], evidence_against=["E9"]),
        ],
    )

    cleaned, dropped = drop_unknown_citations(synthesis, known={"E1", "E2"})

    assert [f.statement for f in cleaned.findings] == ["ok"]
    assert cleaned.findings[0].evidence_ids == ["E1"]
    assert [c.claim for c in cleaned.contradictions] == ["c"]
    assert dropped == 3


def test_verify_citations_counts_unsupported_body_paragraphs_only():
    draft = ReviewDraft(
        title="T",
        sections=[
            ReviewSection(heading="Introduction", paragraphs=[Paragraph(text="context")]),
            ReviewSection(
                heading="SQ1",
                paragraphs=[
                    Paragraph(text="supported", citations=["E1", "E1"]),
                    Paragraph(text="made up", citations=["E42"]),
                ],
            ),
        ],
    )

    checked, report = verify_citations(draft, known={"E1"})

    assert report.unsupported_paragraphs == 1
    assert report.invalid_citations == 1
    assert checked.sections[1].paragraphs[0].citations == ["E1"]


def test_format_reference_handles_missing_metadata():
    full = paper(
        "W1", authors=["A. Smith", "B. Jones", "C. Lee"], year=2023, venue="NAACL", doi="10.1/x"
    )

    assert (
        format_reference(full) == "A. Smith et al. (2023). Paper W1. NAACL. https://doi.org/10.1/x"
    )
    assert format_reference(paper("W2")) == "Unknown author (n.d.). Paper W2."
