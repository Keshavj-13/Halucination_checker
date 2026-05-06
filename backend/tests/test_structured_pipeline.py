import os
import sys

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.schemas import Evidence
from services.claim_extractor import extract_claims
from services.retrieval_pipeline import retrieval_pipeline
from services.verifier import verify_claim
from services.voters.deterministic_voter import deterministic_voter


@pytest.mark.asyncio
async def test_extractor_returns_structured_claims_not_fragments():
    doc = "Albert Einstein was born in 1879 and developed the theory of relativity."
    claims = await extract_claims(doc)
    assert claims, claims
    first = claims[0]
    assert "structured_claim" in first, first
    assert isinstance(first["structured_claim"], dict)
    assert first["structured_claim"].get("subject")
    assert first["claim_type"] in {
        "ENTITY_RELATION",
        "DATE_CLAIM",
        "NUMERIC_CLAIM",
        "SCIENTIFIC",
        "DEFINITION",
        "TEMPORAL",
        "SUBJECTIVE",
        "UNVERIFIABLE",
    }


@pytest.mark.asyncio
async def test_negation_is_detected_and_preserved():
    claims = await extract_claims("The Earth is not flat.")
    assert claims and claims[0]["structured_claim"]["negation"] is True


def test_numeric_conversion_works_across_units():
    claim = "Speed of light is approximately 3 x 10^8 m/s"
    evidence = [
        Evidence(
            title="src",
            snippet="The speed of light in vacuum is 299792 km/s.",
            url="https://nasa.gov/speed",
            support="supporting",
            stance="support",
            reliability_score=0.95,
            source_domain="nasa.gov",
        )
    ]
    out = deterministic_voter.vote(claim, evidence)
    assert out["status"] == "Verified", out


def test_scientific_claim_routes_to_scientific_sources():
    urls = retrieval_pipeline._build_typed_urls("mRNA vaccine efficacy trial", "SCIENTIFIC")
    joined = "\n".join(urls)
    assert "pubmed" in joined
    assert "arxiv" in joined
    assert "openalex" in joined


def test_contradiction_distinguished_from_support():
    claim = "Vaccines contain microchips"
    support = Evidence(
        title="bad",
        snippet="A blog claims vaccines contain chips.",
        url="https://blog.example/post",
        support="supporting",
        stance="support",
        reliability_score=0.3,
        source_domain="blog.example",
    )
    refute = Evidence(
        title="who",
        snippet="Vaccines do not contain microchips.",
        url="https://who.int/fact-check",
        support="contradicting",
        stance="refute",
        reliability_score=0.98,
        source_domain="who.int",
    )
    out = deterministic_voter.vote(claim, [support, refute])
    assert out["status"] in {"Hallucination", "Plausible"}, out
    assert out["metadata"]["refute"] >= out["metadata"]["support"], out


@pytest.mark.asyncio
async def test_subjective_claims_marked_unverifiable_with_proof_trace():
    c = await verify_claim(
        "I think this phone is the best ever",
        claim_type="SUBJECTIVE",
        structured_claim={"claim_type": "SUBJECTIVE", "negation": False},
    )
    assert c.label == "UNVERIFIABLE", c
    for key in [
        "original_claim_text",
        "structured_claim",
        "claim_type",
        "retrieved_evidence",
        "source_urls",
        "comparison_steps",
        "scoring_rationale",
        "final_verdict",
        "confidence",
        "negation_or_temporal_reasoning",
    ]:
        assert key in c.proof_trace, (key, c.proof_trace)
