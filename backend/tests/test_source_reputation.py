from services.retrieval_router import retrieve_wikipedia, retrieve_pubmed, retrieve_evidence
from services.claim_extractor import ClaimTriplet, ClaimType


def test_wikipedia_evidence_has_reliability_and_quality():
    triplet = ClaimTriplet(
        subject="Tesla",
        predicate="headquartered_in",
        predicate_canonical="headquartered_in",
        object="Austin",
        claim_type=ClaimType.ENTITY_RELATION,
    )

    evs = retrieve_wikipedia(triplet)
    assert isinstance(evs, list)
    if evs:
        ev = evs[0]
        assert hasattr(ev, "reliability_score")
        assert ev.reliability_score > 0.0
        assert isinstance(ev.page_quality_signals, dict)
        # page_quality_signals are numeric (pydantic coerces bool->float); check truthiness/thresholds
        assert float(ev.page_quality_signals.get("editable_by_public", 0.0)) >= 0.5
        assert float(ev.page_quality_signals.get("open_editability_score", 0.0)) >= 0.0


def test_pubmed_evidence_has_high_reliability():
    triplet = ClaimTriplet(
        subject="vaccines",
        predicate="cause",
        predicate_canonical="causation",
        object="autism",
        claim_type=ClaimType.SCIENTIFIC,
    )

    evs = retrieve_pubmed(triplet)
    assert isinstance(evs, list)
    if evs:
        ev = evs[0]
        assert ev.reliability_score >= 0.9
        assert ev.page_quality_signals.get("editor_expertise_est") >= 0.9


def test_retrieve_evidence_includes_reliability_and_domain():
    triplet = ClaimTriplet(
        subject="Tesla",
        predicate="founded",
        predicate_canonical="founded_year",
        object="2003",
        claim_type=ClaimType.DATE_CLAIM,
    )
    evs = retrieve_evidence(triplet)
    for ev in evs:
        assert hasattr(ev, "reliability_score")
        assert ev.source_domain != ""
        assert isinstance(ev.page_quality_signals, dict)
