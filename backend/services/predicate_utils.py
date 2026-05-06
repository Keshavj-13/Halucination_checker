from __future__ import annotations

from typing import Optional


_UNIT_TO_METERS = {
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "km": 1000.0,
    "kilometer": 1000.0,
    "kilometers": 1000.0,
    "mi": 1609.344,
    "mile": 1609.344,
    "miles": 1609.344,
}

_SYNONYMS = {
    "reduce": {"reduce", "decrease", "lower", "drop"},
    "increase": {"increase", "raise", "grow", "boost"},
}


def _to_meters(value: float, unit: Optional[str]) -> tuple[float, str]:
    u = (unit or "").strip().lower()
    if u in _UNIT_TO_METERS:
        return float(value) * _UNIT_TO_METERS[u], "m"
    return float(value), u


def numeric_match(v1: float, u1: Optional[str], v2: float, u2: Optional[str]) -> bool:
    a, ua = _to_meters(v1, u1)
    b, ub = _to_meters(v2, u2)
    if ua != ub:
        return False
    tol = max(1e-6, 0.005 * max(abs(a), abs(b), 1.0))
    return abs(a - b) <= tol


def predicate_relation(p1: str, p2: str) -> str:
    a = (p1 or "").strip().lower()
    b = (p2 or "").strip().lower()
    if a == b:
        return "same"

    for family in _SYNONYMS.values():
        if a in family and b in family:
            return "same"

    if {a, b} <= {"increase", "decrease"}:
        return "opposite"
    if {a, b} <= {"raise", "lower"}:
        return "opposite"

    return "different"
