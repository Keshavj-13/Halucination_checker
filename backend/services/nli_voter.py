from __future__ import annotations

import re
from typing import Dict


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9]+", (text or "").lower()))


def _numbers(text: str) -> list[str]:
    return re.findall(r"\b\d+(?:\.\d+)?\b", text or "")


def _negated(text: str) -> bool:
    return bool(re.search(r"\b(not|no|never|cannot|can't|doesn't|do not|did not)\b", (text or "").lower()))


def nli_score(claim: str, evidence: str) -> Dict[str, float]:
    ct = _tokens(claim)
    et = _tokens(evidence)
    overlap = len(ct & et) / max(1, len(ct))

    cn = _numbers(claim)
    en = _numbers(evidence)
    number_conflict = bool(cn and en and cn != en)

    neg_flip = _negated(claim) ^ _negated(evidence)

    entailment = overlap
    contradiction = 0.0

    if number_conflict and overlap >= 0.5:
        contradiction = 0.92
        entailment = min(entailment, 0.08)
    elif neg_flip and overlap >= 0.4:
        contradiction = 0.85
        entailment = min(entailment, 0.15)

    neutral = max(0.0, 1.0 - max(entailment, contradiction))
    return {
        "entailment": round(float(entailment), 4),
        "contradiction": round(float(contradiction), 4),
        "neutral": round(float(neutral), 4),
    }
