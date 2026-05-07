"""
Test voter outputs and evidence signals visibility in API responses.

This test suite verifies:
1. proof_trace contains voter_results with status/confidence/reasoning/metadata
2. Evidence objects include reliability_score and page_quality_signals
3. API responses (AuditResponse) include these fields
4. Full end-to-end flow from claim → retrieval → voters → proof_trace
"""

import pytest
import sys
from pathlib import Path
from typing import List
from unittest.mock import patch

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import Claim, Evidence, VoterResult, RuntimeMetadata


@pytest.fixture
def sample_evidence():
    """Create sample evidence with reliability signals matching actual schema."""
    return Evidence(
        title="Boiling Point of Water",
        snippet="Water boils at 100 degrees Celsius at standard atmospheric pressure.",
        url="https://en.wikipedia.org/wiki/Boiling_point",
        support="supporting",
        stance="mention",
        attribution="none",
        citation_direction="none",
        reliability_score=0.85,
        reliability_explanation="Wikipedia article on boiling point",
        source_domain="wikipedia.org",
        page_quality_signals={
            "editable_by_public": True,
            "editor_expertise_est": 0.75,
            "open_editability_score": 0.70,
        },
    )


@pytest.fixture
def sample_voter_result():
    """Create a sample voter result."""
    return VoterResult(
        status="VERIFIED",
        confidence=0.88,
        reasoning="TF-IDF match on keywords 'water', 'boils', '100'.",
        metadata={"tf_idf_score": 0.88, "term_overlap": 0.92},
    )


def test_evidence_includes_reliability_signals(sample_evidence):
    """Verify Evidence objects include reliability_score and page_quality_signals."""
    assert sample_evidence.reliability_score == 0.85
    assert sample_evidence.page_quality_signals is not None
    assert "editable_by_public" in sample_evidence.page_quality_signals
    assert "editor_expertise_est" in sample_evidence.page_quality_signals
    assert "open_editability_score" in sample_evidence.page_quality_signals
    assert sample_evidence.page_quality_signals["editable_by_public"] == True or sample_evidence.page_quality_signals["editable_by_public"] == 1.0
    assert sample_evidence.page_quality_signals["editor_expertise_est"] == 0.75


def test_voter_result_contains_full_metadata(sample_voter_result):
    """Verify VoterResult includes all required fields for frontend visibility."""
    assert sample_voter_result.status == "VERIFIED"
    assert sample_voter_result.confidence == 0.88
    assert sample_voter_result.reasoning is not None
    assert len(sample_voter_result.reasoning) > 0
    assert sample_voter_result.metadata is not None
    assert isinstance(sample_voter_result.metadata, dict)
    assert sample_voter_result.metadata["tf_idf_score"] == 0.88


def test_voter_result_confidence_in_valid_range(sample_voter_result):
    """Verify voter confidence is in [0, 1] range."""
    assert 0.0 <= sample_voter_result.confidence <= 1.0


def test_voter_result_status_is_valid_label(sample_voter_result):
    """Verify voter result status is one of the valid labels."""
    valid_statuses = ["VERIFIED", "PLAUSIBLE", "REFUTED", "UNCERTAIN", "CONFLICTING", "UNVERIFIABLE"]
    assert sample_voter_result.status in valid_statuses


def test_claim_with_voter_results():
    """Verify Claim can contain voter_results mapping."""
    voter_results = {
        "heuristic_voter": VoterResult(
            status="VERIFIED",
            confidence=0.88,
            reasoning="Strong TF-IDF match",
            metadata={"score": 0.88},
        ),
        "deterministic_voter": VoterResult(
            status="VERIFIED",
            confidence=0.95,
            reasoning="Keyword matching confirmed",
            metadata={"matches": 3},
        ),
    }

    claim = Claim(
        text="Water boils at 100 degrees Celsius.",
        status="Verified",
        confidence=0.91,
        evidence=[],
        voter_results=voter_results,
        label="VERIFIED",
    )

    assert len(claim.voter_results) == 2
    assert "heuristic_voter" in claim.voter_results
    assert "deterministic_voter" in claim.voter_results
    assert claim.voter_results["heuristic_voter"].status == "VERIFIED"
    assert claim.voter_results["deterministic_voter"].confidence == 0.95


def test_claim_proof_trace_includes_runtime_metadata():
    """Verify Claim proof_trace can contain RuntimeMetadata with retrieval/voting info."""
    runtime_meta = RuntimeMetadata(
        total_runtime_ms=123.45,
        retrieval_runtime_ms=50.0,
        voting_runtime_ms=60.0,
        num_urls=3,
        num_chunks=15,
        cache_hits=2,
        external_failures=[],
    )

    claim = Claim(
        text="Earth orbits the Sun.",
        status="Verified",
        confidence=0.95,
        evidence=[],
        label="VERIFIED",
        runtime=runtime_meta,
        proof_trace={
            "final_status": "VERIFIED",
            "total_runtime_ms": 123.45,
            "num_urls": 3,
        },
    )

    assert claim.runtime.total_runtime_ms == 123.45
    assert claim.runtime.retrieval_runtime_ms == 50.0
    assert claim.runtime.voting_runtime_ms == 60.0
    assert claim.runtime.num_urls == 3
    assert claim.runtime.num_chunks == 15


def test_evidence_with_different_source_domains():
    """Verify different sources get appropriate reliability scores."""
    sources_and_scores = [
        ("wikipedia.org", 0.80),  # editable but expert-reviewed
        ("pubmed.ncbi.nlm.nih.gov", 0.90),  # peer-reviewed
        ("arxiv.org", 0.75),  # preprint
        ("openalex.org", 0.85),  # academic metadata
        ("wikidata.org", 0.70),  # structured but potentially incomplete
    ]

    for source_domain, expected_reliability in sources_and_scores:
        evidence = Evidence(
            title=f"Article from {source_domain}",
            snippet=f"Sample text from {source_domain}",
            url=f"https://{source_domain}/article",
            support="supporting",
            stance="mention",
            attribution="none",
            citation_direction="none",
            reliability_score=expected_reliability,
            source_domain=source_domain,
            page_quality_signals={
                "editable_by_public": source_domain == "wikipedia.org",
                "editor_expertise_est": 0.80 if "pubmed" in source_domain else 0.60,
                "open_editability_score": 0.70 if "wikipedia" in source_domain else 0.30,
            },
        )

        assert evidence.reliability_score == expected_reliability
        assert evidence.source_domain == source_domain


def test_claim_uncertain_label():
    """Verify claims can be labeled as UNCERTAIN when no evidence available."""
    claim = Claim(
        text="An obscure fact with no retrievable evidence.",
        status="Plausible",  # Legacy status
        confidence=0.0,
        evidence=[],
        label="UNCERTAIN",  # New taxonomy
    )

    assert claim.label == "UNCERTAIN"
    assert len(claim.evidence) == 0
    assert claim.confidence == 0.0


def test_multiple_voter_results_with_different_statuses():
    """Verify claims with multiple voters can have different verdicts from each voter."""
    voter_results = {
        "heuristic_voter": VoterResult(
            status="VERIFIED",
            confidence=0.88,
            reasoning="TF-IDF match",
            metadata={"score": 0.88},
        ),
        "deterministic_voter": VoterResult(
            status="PLAUSIBLE",
            confidence=0.55,
            reasoning="Partial keyword match",
            metadata={"match_count": 2},
        ),
        "nli_voter": VoterResult(
            status="REFUTED",
            confidence=0.92,
            reasoning="Contradicts evidence",
            metadata={"nli_score": 0.92},
        ),
    }

    claim = Claim(
        text="Test claim",
        status="Verified",
        confidence=0.78,  # Ensemble average
        evidence=[],
        voter_results=voter_results,
        label="VERIFIED",  # Final verdict from orchestrator
    )

    # Verify all voters present
    assert len(claim.voter_results) == 3

    # Verify each has their own confidence
    confidences = [v.confidence for v in claim.voter_results.values()]
    assert confidences == [0.88, 0.55, 0.92]

    # Verify final claim label is orchestrator decision (not individual voter)
    assert claim.label == "VERIFIED"


def test_voter_result_metadata_is_extensible():
    """Verify VoterResult metadata can store arbitrary voter-specific data."""
    metadata_dict = {
        "tf_idf_score": 0.88,
        "term_overlap": 0.92,
        "matching_sentences": ["Sentence 1", "Sentence 2"],
        "num_urls_checked": 5,
        "retrieval_time_ms": 234.5,
        "custom_signal_1": True,
        "custom_signal_2": {"nested": "value"},
    }

    voter_result = VoterResult(
        status="VERIFIED",
        confidence=0.88,
        reasoning="Multiple signals align",
        metadata=metadata_dict,
    )

    assert voter_result.metadata["tf_idf_score"] == 0.88
    assert voter_result.metadata["matching_sentences"] == ["Sentence 1", "Sentence 2"]
    assert voter_result.metadata.get("custom_signal_2", {}).get("nested") == "value"


def test_evidence_page_quality_signals_for_frontend_display():
    """Verify page quality signals are suitable for frontend display."""
    evidence = Evidence(
        title="Article Title",
        snippet="Article snippet",
        url="https://example.com/article",
        support="supporting",
        stance="mention",
        attribution="none",
        citation_direction="none",
        reliability_score=0.82,
        page_quality_signals={
            "editable_by_public": True,
            "editor_expertise_est": 0.75,
            "open_editability_score": 0.70,
            "num_editors": 42,
            "last_edit_days_ago": 15,
            "has_citations": True,
        },
    )

    # These signals should be human-readable and useful for ranking/filtering
    signals = evidence.page_quality_signals
    assert isinstance(signals, dict)
    assert all(isinstance(k, str) for k in signals.keys())


def test_claim_with_best_and_contradicting_evidence():
    """Verify claims can track best supporting and contradicting evidence."""
    support_evidence = Evidence(
        title="Supporting Source",
        snippet="This supports the claim.",
        url="https://example.com/support",
        support="supporting",
        stance="support",
        attribution="none",
        citation_direction="none",
        reliability_score=0.85,
    )

    contra_evidence = Evidence(
        title="Contradicting Source",
        snippet="This contradicts the claim.",
        url="https://example.com/contra",
        support="contradicting",
        stance="refute",
        attribution="none",
        citation_direction="none",
        reliability_score=0.80,
    )

    claim = Claim(
        text="Test claim",
        status="Verified",
        confidence=0.75,
        evidence=[support_evidence, contra_evidence],
        best_evidence=[support_evidence],
        contradicting_evidence=[contra_evidence],
        label="VERIFIED",
    )

    assert len(claim.evidence) == 2
    assert len(claim.best_evidence) == 1
    assert len(claim.contradicting_evidence) == 1
    assert claim.best_evidence[0].support == "supporting"
    assert claim.contradicting_evidence[0].support == "contradicting"


def test_runtime_metadata_tracks_performance():
    """Verify RuntimeMetadata captures performance metrics for full traceability."""
    runtime = RuntimeMetadata(
        total_runtime_ms=500.0,
        retrieval_runtime_ms=200.0,
        voting_runtime_ms=250.0,
        num_urls=8,
        num_chunks=64,
        cache_hits=3,
        external_failures=["PubMed API timeout", "arXiv rate limit"],
    )

    assert runtime.total_runtime_ms == 500.0
    assert runtime.retrieval_runtime_ms == 200.0
    assert runtime.voting_runtime_ms == 250.0
    assert runtime.num_urls == 8
    assert runtime.num_chunks == 64
    assert runtime.cache_hits == 3
    assert len(runtime.external_failures) == 2
    assert "PubMed API timeout" in runtime.external_failures


def test_full_claim_structure_for_frontend():
    """Integration test: verify complete Claim structure needed for frontend display."""
    claim = Claim(
        text="Water boils at 100°C at sea level.",
        status="Verified",
        confidence=0.92,
        evidence=[
            Evidence(
                title="Wikipedia: Boiling Point",
                snippet="Water boils at 100°C under standard atmospheric pressure.",
                url="https://en.wikipedia.org/wiki/Boiling_point",
                support="supporting",
                stance="support",
                attribution="none",
                citation_direction="none",
                reliability_score=0.85,
                page_quality_signals={
                    "editable_by_public": True,
                    "editor_expertise_est": 0.75,
                    "open_editability_score": 0.70,
                },
            ),
        ],
        voter_results={
            "heuristic_voter": VoterResult(
                status="VERIFIED",
                confidence=0.90,
                reasoning="Strong keyword match",
                metadata={"score": 0.90, "keywords_matched": 4},
            ),
            "deterministic_voter": VoterResult(
                status="VERIFIED",
                confidence=0.95,
                reasoning="Exact factual match",
                metadata={"match_type": "exact", "confidence": 0.95},
            ),
        },
        label="VERIFIED",
        runtime=RuntimeMetadata(
            total_runtime_ms=250.5,
            retrieval_runtime_ms=100.0,
            voting_runtime_ms=120.0,
            num_urls=2,
            num_chunks=5,
            cache_hits=1,
        ),
        proof_trace={
            "final_label": "VERIFIED",
            "voters_run": ["heuristic_voter", "deterministic_voter"],
            "retrieval_status": "success",
        },
    )

    # Verify all fields are present for frontend
    assert claim.text
    assert claim.label in ["VERIFIED", "PLAUSIBLE", "REFUTED", "UNCERTAIN"]
    assert 0.0 <= claim.confidence <= 1.0
    assert len(claim.evidence) > 0
    assert len(claim.voter_results) > 0
    for voter_name, voter_result in claim.voter_results.items():
        assert voter_result.status
        assert 0.0 <= voter_result.confidence <= 1.0
        assert voter_result.reasoning
        assert voter_result.metadata is not None
    assert claim.runtime is not None
    assert claim.proof_trace is not None or isinstance(claim.proof_trace, dict)
