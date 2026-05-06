import inspect
import time


def test_full_pipeline_determinism():
    """
    Same input must always produce identical output.
    """
    from services.verifier import audit_claim

    claim = "Tesla was founded in 2003."

    r1 = audit_claim(claim)
    r2 = audit_claim(claim)

    assert r1 == r2


def test_triplet_extraction_basic():
    from services.claim_extractor import extract_triplets

    text = "Tesla was founded in 2003 by Martin Eberhard."
    triplets = extract_triplets(text)

    assert len(triplets) >= 2

    preds = {t.predicate_canonical for t in triplets}

    assert "founded_year" in preds
    assert "founded_by" in preds


def test_negation_detection():
    from services.claim_extractor import extract_triplets

    text = "Vaccines do not cause autism."
    triplets = extract_triplets(text)

    assert any(t.negated for t in triplets)


def test_subjective_filtering():
    from services.claim_extractor import extract_triplets

    text = "This is the best phone ever."
    triplets = extract_triplets(text)

    assert len(triplets) == 0


def test_numeric_equivalence():
    from services.predicate_utils import numeric_match

    assert numeric_match(8.848, "km", 8848, "m") is True
    assert numeric_match(100, "km", 62.14, "mi") is True


def test_numeric_mismatch():
    from services.predicate_utils import numeric_match

    assert numeric_match(100, "km", 50, "km") is False


def test_predicate_synonyms():
    from services.predicate_utils import predicate_relation

    assert predicate_relation("reduce", "decrease") == "same"


def test_predicate_antonyms():
    from services.predicate_utils import predicate_relation

    assert predicate_relation("increase", "decrease") == "opposite"


def test_entity_claim_routes_to_wikidata(monkeypatch):
    from services.retrieval_router import retrieve_evidence
    from services.claim_extractor import ClaimTriplet, ClaimType

    called = {"wikidata": False}

    def fake_wikidata(*args, **kwargs):
        called["wikidata"] = True
        return []

    monkeypatch.setattr(
        "services.retrieval_router.retrieve_wikidata",
        fake_wikidata,
    )

    triplet = ClaimTriplet(
        subject="Tesla",
        predicate="found",
        predicate_canonical="founded_year",
        object="2003",
        claim_type=ClaimType.DATE_CLAIM,
    )

    retrieve_evidence(triplet)

    assert called["wikidata"] is True


def test_scientific_claim_routes_to_pubmed(monkeypatch):
    from services.retrieval_router import retrieve_evidence
    from services.claim_extractor import ClaimTriplet, ClaimType

    called = {"pubmed": False}

    def fake_pubmed(*args, **kwargs):
        called["pubmed"] = True
        return []

    monkeypatch.setattr(
        "services.retrieval_router.retrieve_pubmed",
        fake_pubmed,
    )

    triplet = ClaimTriplet(
        subject="Smoking",
        predicate="cause",
        predicate_canonical="causes",
        object="cancer",
        claim_type=ClaimType.SCIENTIFIC,
    )

    retrieve_evidence(triplet)

    assert called["pubmed"] is True


def test_wikidata_exact_match():
    from services.verifier import audit_claim

    claim = "Tesla was founded in 2003."

    result = audit_claim(claim)

    assert result["verdict"] in ["VERIFIED", "PLAUSIBLE"]


def test_nli_support_vs_contradiction():
    from services.nli_voter import nli_score

    support = nli_score(
        "Tesla was founded in 2003",
        "Tesla, Inc. was founded in 2003.",
    )

    contradiction = nli_score(
        "Tesla was founded in 2003",
        "Tesla was founded in 2006.",
    )

    assert support["entailment"] > support["contradiction"]
    assert contradiction["contradiction"] > contradiction["entailment"]


def test_negation_flips_verdict(monkeypatch):
    from services.verifier import audit_claim

    claim = "Vaccines do not cause autism."

    result = audit_claim(claim)

    assert result["verdict"] in ["VERIFIED", "PLAUSIBLE"]


def test_no_evidence_returns_uncertain(monkeypatch):
    from services.verifier import audit_claim

    def fake_retrieval(*args, **kwargs):
        return []

    monkeypatch.setattr(
        "services.retrieval_router.retrieve_evidence",
        fake_retrieval,
    )

    result = audit_claim("Some obscure unknown claim")

    assert result["verdict"] in ["UNCERTAIN", "UNVERIFIABLE"]


def test_proof_trace_structure():
    from services.verifier import audit_claim

    result = audit_claim("Tesla was founded in 2003.")

    assert "proof_trace" in result
    assert "steps" in result["proof_trace"]

    step = result["proof_trace"]["steps"][0]

    assert "claim_structured" in step
    assert "verdict" in step


def test_multi_claim_input():
    from services.verifier import audit_claim

    text = "Tesla was founded in 2003. It is headquartered in Austin."

    result = audit_claim(text)

    assert len(result["triplet_results"]) >= 2


def test_no_cosine_similarity_used():
    import services

    source = inspect.getsource(services)

    assert "cosine_similarity" not in source


def test_no_duckduckgo_usage():
    import services

    source = inspect.getsource(services)

    assert "duckduckgo" not in source.lower()


def test_no_llm_usage():
    import services

    source = inspect.getsource(services)

    forbidden = ["openai", "gemini", "gpt", "llm"]

    for f in forbidden:
        assert f not in source.lower()


def test_runtime_bound():
    from services.verifier import audit_claim

    start = time.time()
    audit_claim("Tesla was founded in 2003.")
    duration = time.time() - start

    assert duration < 5.0
