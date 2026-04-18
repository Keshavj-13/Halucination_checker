import random
import re
from typing import List
from models.schemas import Claim, Evidence

# Fake evidence pool to pull from randomly
_EVIDENCE_POOL = [
    Evidence(
        title="Reuters Fact Check",
        snippet="A review of available sources found this claim to be broadly consistent with known data.",
        url="https://www.reuters.com/fact-check/placeholder",
        support="supporting",
    ),
    Evidence(
        title="Nature – Peer-Reviewed Study",
        snippet="Research published in Nature supports the general validity of this statement.",
        url="https://www.nature.com/articles/placeholder",
        support="supporting",
    ),
    Evidence(
        title="Wikipedia – Related Topic",
        snippet="The article provides context but does not fully corroborate the specific claim.",
        url="https://en.wikipedia.org/wiki/placeholder",
        support="weak",
    ),
    Evidence(
        title="PolitiFact Analysis",
        snippet="Rated this type of claim as Mostly True based on available evidence.",
        url="https://www.politifact.com/article/placeholder",
        support="supporting",
    ),
    Evidence(
        title="Snopes Investigation",
        snippet="Several aspects of this claim lack verifiable sources.",
        url="https://www.snopes.com/fact-check/placeholder",
        support="weak",
    ),
    Evidence(
        title="Academic Journal – Springer",
        snippet="Quantitative data cited in this claim aligns with measurements reported across multiple studies.",
        url="https://link.springer.com/article/placeholder",
        support="supporting",
    ),
]

import logging

logger = logging.getLogger("audit-api.verifier")

_HALLUCINATION_TRIGGERS = {"best", "always", "never", "every", "all", "worst", "perfect", "impossible", "guaranteed"}
_NUMBER_PATTERN = re.compile(r'\d')


def verify_claim(text: str) -> Claim:
    """Determine status + confidence + fake evidence for a claim."""
    logger.debug(f"Verifying claim: {text[:50]}...")
    lower = text.lower()
    words = set(lower.split())

    has_numbers = bool(_NUMBER_PATTERN.search(text))
    has_trigger = bool(words & _HALLUCINATION_TRIGGERS)

    if has_trigger:
        status = "Hallucination"
        confidence = round(random.uniform(0.70, 0.88), 2)
    elif has_numbers:
        status = "Verified"
        confidence = round(random.uniform(0.80, 0.95), 2)
    else:
        status = "Plausible"
        confidence = round(random.uniform(0.55, 0.78), 2)

    # Pick 1 or 2 evidence items
    count = random.choice([1, 2])
    evidence = random.sample(_EVIDENCE_POOL, count)

    return Claim(text=text, status=status, confidence=confidence, evidence=evidence)


def verify_claims(claims: List[str]) -> List[Claim]:
    return [verify_claim(c) for c in claims]
