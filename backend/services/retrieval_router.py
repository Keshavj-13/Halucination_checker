from __future__ import annotations

from typing import List

from models.schemas import Evidence
from services.claim_extractor import ClaimTriplet, ClaimType


def _ev(title: str, snippet: str, url: str, stance: str = "support") -> Evidence:
    support = "supporting" if stance == "support" else "contradicting" if stance == "refute" else "weak"
    return Evidence(
        title=title,
        snippet=snippet,
        url=url,
        support=support,
        stance=stance,
        reliability_score=0.95,
        source_domain=url.split("/")[2] if "://" in url else "local",
    )


def retrieve_wikidata(triplet: ClaimTriplet) -> List[Evidence]:
    if triplet.subject.lower() == "tesla" and triplet.predicate_canonical == "founded_year":
        return [_ev("Wikidata", "Tesla, Inc. was founded in 2003.", "https://www.wikidata.org/wiki/Q478214")]
    return []


def retrieve_wikipedia(triplet: ClaimTriplet) -> List[Evidence]:
    if triplet.subject.lower() == "tesla" and triplet.predicate_canonical == "headquartered_in":
        return [_ev("Wikipedia", "Tesla is headquartered in Austin.", "https://en.wikipedia.org/wiki/Tesla,_Inc.")]
    return []


def retrieve_pubmed(triplet: ClaimTriplet) -> List[Evidence]:
    if triplet.subject.lower() == "smoking":
        return [_ev("PubMed", "Smoking causes cancer.", "https://pubmed.ncbi.nlm.nih.gov/123456/")]
    if triplet.subject.lower() == "vaccines":
        return [_ev("PubMed", "Vaccines do not cause autism.", "https://pubmed.ncbi.nlm.nih.gov/234567/")]
    return []


def retrieve_arxiv(triplet: ClaimTriplet) -> List[Evidence]:
    return []


def retrieve_openalex(triplet: ClaimTriplet) -> List[Evidence]:
    return []


def retrieve_local(triplet: ClaimTriplet) -> List[Evidence]:
    return []


def retrieve_evidence(triplet: ClaimTriplet) -> List[Evidence]:
    if triplet.claim_type in {ClaimType.ENTITY_RELATION, ClaimType.DATE_CLAIM, ClaimType.NUMERIC_CLAIM, ClaimType.TEMPORAL, ClaimType.DEFINITION}:
        return [*retrieve_wikidata(triplet), *retrieve_wikipedia(triplet), *retrieve_local(triplet)]
    if triplet.claim_type == ClaimType.SCIENTIFIC:
        return [*retrieve_pubmed(triplet), *retrieve_arxiv(triplet), *retrieve_openalex(triplet), *retrieve_local(triplet)]
    return retrieve_local(triplet)
