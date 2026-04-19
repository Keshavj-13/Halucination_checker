from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple

from models.schemas import Evidence
from services.voters.base import Voter


_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "at", "by", "with", "from", "as", "is", "are",
    "was", "were", "be", "been", "being", "that", "this", "these", "those", "it", "its", "their", "his", "her",
}

def _compile_terms(terms: List[str]) -> re.Pattern:
    escaped = "|".join(re.escape(t) for t in terms)
    return re.compile(rf"\b(?:{escaped})\b", re.IGNORECASE)


SUPPORT_TERMS = [
    "is", "are", "was", "were", "equals", "equal", "measured", "confirmed", "show", "shows", "demonstrate",
    "demonstrates", "observed", "verified", "recorded", "reported", "officially", "documented", "established",
    "proven", "indicates", "indicate", "found", "study", "studies", "evidence", "supported", "supports",
    "consistent", "agrees", "aligns", "matches", "validated", "reproduced", "replicated", "peer-reviewed",
    "census", "survey", "registry", "official statistics", "according to data", "data show", "data shows",
    "analysis shows", "observational", "experiment", "experimental", "benchmark", "specification", "standard",
    "complies", "conforms", "meets", "true", "correct", "accurate", "fact", "factual", "confirmed by",
    "corroborated", "cross-checked", "independently verified", "supported by", "endorsed by", "source confirms",
    "court record", "public record", "published", "journal", "meta-analysis", "systematic review",
]

REFUTE_TERMS = [
    "false", "incorrect", "debunked", "contradicts", "contradict", "refute", "refutes", "refuted", "not true",
    "myth", "fabricated", "unsupported", "misleading", "inaccurate", "wrong", "error", "erroneous", "disputed",
    "retracted", "withdrawn", "no evidence", "no proof", "cannot be verified", "fails", "invalid", "invalidated",
    "contrary", "inconsistent", "does not", "did not", "never happened", "fake", "hoax", "misquote", "outdated",
    "superseded", "obsolete", "misinterpreted", "distorted", "manipulated", "unreliable", "unfounded", "baseless",
    "exaggerated", "overstated", "understated", "cherry-picked", "debunk", "fact-check false", "fact check false",
    "denied", "rebutted", "not supported", "not consistent", "contradicted", "counterevidence", "counter-evidence",
    "fails replication", "not reproducible", "major flaw", "methodological flaw", "incorrectly claims",
]

NEUTRAL_TERMS = [
    "some believe", "the theory", "it is claimed", "reportedly", "allegedly", "according to", "rumor", "unconfirmed",
    "speculation", "suggests", "may", "might", "could", "possibly", "appears", "seems", "opinion", "commentary",
    "editorial", "analysis", "narrative", "perspective", "quoted", "quote", "said", "stated", "claims", "claims that",
    "purports", "asserts", "not verified", "pending confirmation", "preliminary", "early report", "anecdotal",
    "hearsay", "report", "news report", "blog post", "forum post", "social media", "discussion", "debate",
    "hypothesis", "possible", "unclear", "ambiguous", "mixed evidence", "inconclusive", "suggestive", "if true",
]

_SUPPORT_CUES = _compile_terms(SUPPORT_TERMS)
_REFUTE_CUES = _compile_terms(REFUTE_TERMS)
_NEUTRAL_CUES = _compile_terms(NEUTRAL_TERMS)

RELATION_PATTERNS: List[Tuple[str, str]] = [
    (r"\borbit(s|ing|ed)?\b|\brevolve(s|d|ing)?\b|\brotation\b", "orbit"),
    (r"\bdistance\b|\bau\b|\bmillion\s+miles\b|\bkilometer(s)?\b|\bkm\b|\blight[- ]year(s)?\b", "distance"),
    (r"\bspeed\b|\bvelocity\b|\bmph\b|\bkm/h\b|\bm\/s\b|\bacceleration\b", "speed"),
    (r"\btemperature\b|\bcelsius\b|\bfahrenheit\b|\bkelvin\b|\bheat\b|\bcold\b", "temperature"),
    (r"\bpopulation\b|\bcensus\b|\binhabitants\b", "population"),
    (r"\bcapital\b|\bcapital city\b", "capital"),
    (r"\bborn\b|\bbirth\b|\bbirthplace\b", "birth"),
    (r"\bdied\b|\bdeath\b|\bdeceased\b", "death"),
    (r"\binvent(ed|ion)?\b|\bdiscover(ed|y)?\b|\bfound(ed|er)?\b|\borigin\b", "origin"),
    (r"\bcauses?\b|\bleads? to\b|\bresults? in\b|\bdue to\b|\bbecause\b", "causal"),
    (r"\bdate\b|\byear\b|\bon\s+\w+\s+\d{1,2},?\s+\d{4}\b|\btimeline\b", "date"),
    (r"\bapi\b|\bmethod\b|\bfunction\b|\bendpoint\b|\bparameter\b|\breturns?\b", "api"),
    (r"\bunit\b|\bkg\b|\bkm\b|\bmiles\b|\bmeters?\b|\bseconds?\b|\bms\b", "unit"),
    (r"\bprice\b|\bcost\b|\bvalue\b|\bmarket cap\b|\bvaluation\b", "finance"),
    (r"\bapproved\b|\bregulation\b|\blegal\b|\blaw\b|\bstatute\b|\bruling\b", "legal"),
    (r"\befficacy\b|\beffectiveness\b|\btrial\b|\brct\b|\bclinical\b", "medical"),
]

RELATION_CUES: Dict[str, str] = {
    "orbit": r"\borbit(s|ing|ed)?\b|\brevolv(es|ed|ing)?\b|\brotation\b",
    "distance": r"\bdistance\b|\bau\b|\bkilometer(s)?\b|\bkm\b|\bmiles\b|\blight[- ]year(s)?\b",
    "speed": r"\bspeed\b|\bvelocity\b|\bmph\b|\bkm/h\b|\bm\/s\b|\bacceleration\b",
    "temperature": r"\btemperature\b|\bcelsius\b|\bfahrenheit\b|\bkelvin\b|\bheat\b|\bcold\b",
    "population": r"\bpopulation\b|\bcensus\b|\binhabitants\b",
    "capital": r"\bcapital\b|\bcapital city\b",
    "birth": r"\bborn\b|\bbirth\b|\bbirthplace\b",
    "death": r"\bdied\b|\bdeath\b|\bdeceased\b",
    "origin": r"\binvent(ed|ion)?\b|\bdiscover(ed|y)?\b|\bfound(ed|er)?\b|\borigin\b",
    "causal": r"\bcauses?\b|\bleads? to\b|\bresults? in\b|\bdue to\b|\bbecause\b",
    "date": r"\b(19|20)\d{2}\b|\bon\s+\w+\s+\d{1,2},?\s+(19|20)\d{2}\b|\btimeline\b",
    "api": r"\bapi\b|\bmethod\b|\bfunction\b|\bendpoint\b|\bparameter\b|\breturns?\b",
    "unit": r"\bkg\b|\bkm\b|\bmiles\b|\bmeters?\b|\bseconds?\b|\bms\b|\bunit\b",
    "finance": r"\bprice\b|\bcost\b|\bvalue\b|\bmarket cap\b|\bvaluation\b|\brevenue\b",
    "legal": r"\bapproved\b|\bregulation\b|\blegal\b|\blaw\b|\bstatute\b|\bruling\b",
    "medical": r"\befficacy\b|\beffectiveness\b|\btrial\b|\brct\b|\bclinical\b",
}

TECHNICAL_TERMS = {
    "equation", "ohm", "voltage", "current", "resistance", "power", "algorithm", "complexity", "gpu", "matrix",
    "clock", "frequency", "latency", "throughput", "control system", "reinforcement", "liquid cooling", "heat transfer",
    "battery", "lithium", "api", "endpoint", "function", "unit", "constraint", "physics", "thermodynamics",
}

MEDICAL_TERMS = {
    "antibiotic", "antibiotics", "vaccine", "vaccines", "insulin", "glucose", "cancer", "smoking", "lung",
    "infection", "viral", "bacterial", "immune", "treatment", "drug", "dose", "clinical", "trial", "health",
}

SAFETY_TERMS = {
    "medical", "medicine", "drug", "dosage", "insulin", "infection", "cancer", "vaccine", "surgery", "diagnosis",
    "electric", "electrical", "high voltage", "fire", "explosive", "toxic", "poison", "radiation", "nuclear",
    "emergency", "critical", "hazard", "dangerous", "safety", "fatal", "death", "lung", "smoking",
}

AUTHORITATIVE_DOMAIN_SUFFIXES = {
    ".gov", ".edu", "who.int", "cdc.gov", "nih.gov", "fda.gov", "ema.europa.eu", "nhs.uk", "mayoclinic.org",
    "nejm.org", "thelancet.com", "bmj.com", "nature.com", "science.org", "cochranelibrary.com",
}

KNOWN_CONSTRAINTS: List[Tuple[re.Pattern, int, str]] = [
    (re.compile(r"\bohm.?s law\b.*\bv\s*=\s*i\s*\*?\s*r\b", re.IGNORECASE), 1, "ohm_law_true"),
    (re.compile(r"\bohm.?s law\b.*\bv\s*=\s*i\s*/\s*r\b", re.IGNORECASE), -1, "ohm_law_false"),
    (re.compile(r"\bpower\b.*\b(voltage\s*\*\s*current|p\s*=\s*v\s*\*?\s*i)\b", re.IGNORECASE), 1, "power_true"),
    (re.compile(r"\bpower\b.*\b(current\s*/\s*voltage|p\s*=\s*i\s*/\s*v)\b", re.IGNORECASE), -1, "power_false"),
    (re.compile(r"\bdivision by zero\b.*\bundefined\b", re.IGNORECASE), 1, "div_zero_true"),
    (re.compile(r"\bheat\b.*\bflows?\b.*\bcold\b.*\bhot\b.*\bnaturally\b", re.IGNORECASE), -1, "thermo_false"),
    (re.compile(r"\bsmoking\b.*\b(improves?|benefits?)\b.*\blung\b", re.IGNORECASE), -1, "smoking_false"),
    (re.compile(r"\bsmoking\b.*\bincreases?\b.*\brisk\b.*\blung cancer\b", re.IGNORECASE), 1, "smoking_true"),
    (re.compile(r"\bantibiotics?\b.*\bviral\b", re.IGNORECASE), -1, "antibiotic_false"),
    (re.compile(r"\bantibiotics?\b.*\bbacterial\b", re.IGNORECASE), 1, "antibiotic_true"),
    (re.compile(r"\bvaccines?\b.*\bmicrochips?\b", re.IGNORECASE), -1, "vaccine_microchip_false"),
    (re.compile(r"\binsulin\b.*\braises?\b.*\bblood sugar\b", re.IGNORECASE), -1, "insulin_false"),
    (re.compile(r"\binsulin\b.*\bregulates?\b.*\bglucose\b", re.IGNORECASE), 1, "insulin_true"),
    (re.compile(r"\bif\s+a\s*>\s*b\s+and\s+b\s*>\s*c\s*,?\s*then\s+a\s*>\s*c\b", re.IGNORECASE), 1, "transitivity_true"),
    (re.compile(r"\bsorting algorithm\b.*\bo\(1\)\b.*\barbitrary input\b", re.IGNORECASE), -1, "sorting_false"),
    (
        re.compile(
            r"\b(ai|artificial intelligence)\b.*\b(replace|eliminate|remove)\b.*\b(all|every)\b.*\b(developer|programmer|engineer)s?\b.*\b(next\s+(month|week)|in\s+\d+\s+(days?|weeks?))\b",
            re.IGNORECASE,
        ),
        -1,
        "ai_total_replacement_nearterm_false",
    ),
    (
        re.compile(r"\b(single|one)\b.*\bpaper\b.*\b(cures?|proof)\b.*\b(all|every)\b.*\bcancer(s)?\b", re.IGNORECASE),
        -1,
        "single_paper_cure_all_false",
    ),
]


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9_]+", (text or "").lower())


def _content_tokens(text: str) -> List[str]:
    return [t for t in _tokens(text) if len(t) > 2 and t not in _STOP]


def _extract_relation(claim: str) -> str:
    lower = (claim or "").lower()
    for pat, rel in RELATION_PATTERNS:
        if re.search(pat, lower):
            return rel

    if re.search(r"\b(best|worst|better|good|bad)\b", lower):
        return "subjective"
    return "general"


def _detect_stance(evidence: Evidence) -> int:
    stance = (evidence.stance or "").lower()
    if stance == "support":
        return 1
    if stance == "refute":
        return -1
    if stance in {"mention", "quotation", "reported_belief", "neutral"}:
        return 0

    txt = f"{evidence.title} {evidence.snippet}".lower()
    if _REFUTE_CUES.search(txt):
        return -1
    if _SUPPORT_CUES.search(txt):
        return 1
    if _NEUTRAL_CUES.search(txt):
        return 0
    return 0


def _relation_match(claim: str, evidence: Evidence, relation: str) -> float:
    text = f"{evidence.title} {evidence.snippet}".lower()
    if relation == "subjective":
        return 0.1
    if relation == "general":
        c = set(_content_tokens(claim))
        e = set(_content_tokens(text))
        return (len(c & e) / max(1, len(c))) if c else 0.0

    c = set(_content_tokens(claim))
    e = set(_content_tokens(text))
    lexical = (len(c & e) / max(1, len(c))) if c else 0.0

    cue = RELATION_CUES.get(relation)
    if cue and re.search(cue, text):
        # Prevent cross-claim bleed-through where a relation term matches but entities do not.
        return min(1.0, 0.3 + 0.7 * lexical)

    return min(0.6, lexical)


def _entity_match(claim: str, evidence: Evidence) -> float:
    c = set(_content_tokens(claim))
    e = set(_content_tokens(f"{evidence.title} {evidence.snippet}"))
    if not c:
        return 0.0
    return min(1.0, len(c & e) / len(c))


def _extract_numbers_with_units(text: str) -> List[Tuple[float, str]]:
    pairs = []
    sci = re.findall(r"(\d+(?:\.\d+)?)\s*[x×]\s*10\s*\^\s*([+-]?\d+)", text or "", flags=re.IGNORECASE)
    for base, exp in sci:
        try:
            pairs.append((float(base) * (10 ** int(exp)), ""))
        except Exception:
            pass

    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*([a-zA-Z%]+)?\b", text or ""):
        value = float(m.group(1))
        unit = (m.group(2) or "").lower()
        pairs.append((value, unit))
    return pairs


def _normalize_unit(value: float, unit: str) -> Tuple[float, str]:
    u = (unit or "").lower()
    if u in {"km", "kilometer", "kilometers"}:
        return value, "km"
    if u in {"m", "meter", "meters"}:
        return value / 1000.0, "km"
    if u in {"mile", "miles", "mi"}:
        return value * 1.60934, "km"
    if u in {"au", "astronomicalunit", "astronomicalunits"}:
        return value * 149_597_870.7, "km"
    if u in {"c", "celsius"}:
        return value, "c"
    if u in {"f", "fahrenheit"}:
        return (value - 32.0) * (5.0 / 9.0), "c"
    if u in {"k", "kelvin"}:
        return value - 273.15, "c"
    if u in {"%", "percent"}:
        return value, "%"
    return value, u


def _numeric_match(claim: str, evidence: Evidence) -> float:
    cn = [_normalize_unit(v, u) for v, u in _extract_numbers_with_units(claim)]
    if not cn:
        return 1.0

    en = [_normalize_unit(v, u) for v, u in _extract_numbers_with_units(evidence.snippet)]
    if not en:
        return 0.0

    matches = 0
    for cv, cu in cn:
        ok = False
        for ev, eu in en:
            if cu and eu and cu != eu:
                continue
            tol = max(1e-6, 0.05 * abs(cv))
            if abs(cv - ev) <= tol:
                ok = True
                break
        matches += int(ok)
    return matches / max(1, len(cn))


def _is_technical_claim(claim: str) -> bool:
    c = (claim or "").lower()
    return any(term in c for term in TECHNICAL_TERMS) or bool(re.search(r"\b(v\s*=|p\s*=|o\(\d+\)|km/s|m/s)\b", c))


def _is_medical_claim(claim: str) -> bool:
    c = (claim or "").lower()
    return any(term in c for term in MEDICAL_TERMS)


def _is_safety_critical(claim: str) -> bool:
    c = (claim or "").lower()
    return any(term in c for term in SAFETY_TERMS)


def _is_authoritative_domain(domain: str) -> bool:
    d = (domain or "").lower()
    return any(d.endswith(sfx) or d == sfx for sfx in AUTHORITATIVE_DOMAIN_SUFFIXES)


def _constraint_signal(claim: str) -> Tuple[int, str]:
    for pat, signal, name in KNOWN_CONSTRAINTS:
        if pat.search(claim or ""):
            return signal, name
    return 0, ""


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _get_tuning() -> Dict[str, float]:
    return {
        "verify_ratio": max(1.05, _float_env("DET_VERIFY_RATIO", 2.0)),
        "hallucination_ratio": max(1.05, _float_env("DET_HALLUCINATION_RATIO", 2.0)),
        "strong_refute_rel_threshold": max(0.0, min(1.0, _float_env("DET_STRONG_REFUTE_REL_THRESHOLD", 0.7))),
        "strong_refute_reliability_threshold": max(0.0, min(1.0, _float_env("DET_STRONG_REFUTE_RELIABILITY_THRESHOLD", 0.75))),
        "contradiction_rel_threshold": max(0.0, min(1.0, _float_env("DET_CONTRADICTION_REL_THRESHOLD", 0.65))),
        "contradiction_reliability_threshold": max(0.0, min(1.0, _float_env("DET_CONTRADICTION_RELIABILITY_THRESHOLD", 0.65))),
        "strong_evidence_strength_threshold": max(0.0, _float_env("DET_STRONG_EVIDENCE_THRESHOLD", 0.08)),
        "verified_support_floor": max(0.0, _float_env("DET_VERIFIED_SUPPORT_FLOOR", 0.8)),
    }


class DeterministicVoter(Voter):
    """Strict non-LLM reasoning voter with relation and numeric constraints."""

    def vote(self, claim: str, evidence: List[Evidence]) -> Dict[str, Any]:
        tuning = _get_tuning()

        if not evidence:
            return {
                "status": "Plausible",
                "confidence": 0.15,
                "reasoning": "No evidence found; deterministic rule returns Uncertain.",
                "score": 0.5,
                "metadata": {"deterministic_label": "Uncertain", "support": 0.0, "refute": 0.0},
            }

        relation = _extract_relation(claim)
        is_technical = _is_technical_claim(claim)
        is_medical = _is_medical_claim(claim)
        is_safety = _is_safety_critical(claim)
        constraint_sig, constraint_name = _constraint_signal(claim)

        support = 0.0
        refute = 0.0
        strong_support_domains = set()
        high_trust_support_count = 0
        authoritative_support_count = 0
        direct_support_count = 0
        contradiction_exists = False
        strong_refute_override = False
        strong_evidence_seen = False
        warning = ""

        per_evidence = []

        if constraint_sig > 0:
            support += 0.9
            strong_evidence_seen = True
        elif constraint_sig < 0:
            refute += 0.9
            strong_evidence_seen = True
            strong_refute_override = True

        for ev in evidence:
            reliability = float(max(0.0, min(ev.reliability_score, 1.0)))
            if reliability < 0.3:
                continue

            stance = _detect_stance(ev)
            rel_match = float(max(0.0, min(_relation_match(claim, ev, relation), 1.0)))
            ent_match = float(max(0.0, min(_entity_match(claim, ev), 1.0)))
            num_match = float(max(0.0, min(_numeric_match(claim, ev), 1.0)))

            ev.relation_match = rel_match
            ev.entity_match = ent_match
            ev.numeric_match = num_match

            bias_penalty = float(max(0.0, min(ev.bias_penalty, 1.0)))
            effective_reliability = reliability * (1.0 - bias_penalty)
            if ev.sponsorship_flag:
                effective_reliability *= 0.5

            evidence_strength = (
                float(stance)
                * effective_reliability
                * rel_match
                * (0.5 + 0.5 * ent_match)
                * (0.5 + 0.5 * num_match)
            )

            if abs(evidence_strength) >= tuning["strong_evidence_strength_threshold"]:
                strong_evidence_seen = True

            if evidence_strength > 0:
                support += evidence_strength
            elif evidence_strength < 0:
                refute += abs(evidence_strength)
                if (
                    rel_match > tuning["contradiction_rel_threshold"]
                    and effective_reliability >= tuning["contradiction_reliability_threshold"]
                ):
                    contradiction_exists = True

            direct_match = rel_match > 0.7 and (ent_match >= 0.4 or num_match >= 0.4)
            if evidence_strength > 0 and direct_match:
                direct_support_count += 1

            if evidence_strength > 0 and effective_reliability >= 0.75:
                high_trust_support_count += 1
                if _is_authoritative_domain(ev.source_domain):
                    authoritative_support_count += 1

            if evidence_strength > 0 and effective_reliability >= 0.65 and rel_match > 0.7:
                domain = (ev.source_domain or ev.url or "").strip().lower()
                if domain:
                    strong_support_domains.add(domain)

            if (
                stance < 0
                and effective_reliability >= tuning["strong_refute_reliability_threshold"]
                and rel_match > tuning["strong_refute_rel_threshold"]
                and (ent_match >= 0.6 or num_match >= 0.6)
            ):
                strong_refute_override = True

            per_evidence.append(
                {
                    "url": ev.url,
                    "stance": stance,
                    "relation_match": round(rel_match, 4),
                    "entity_match": round(ent_match, 4),
                    "numeric_match": round(num_match, 4),
                    "effective_reliability": round(effective_reliability, 4),
                    "evidence_strength": round(evidence_strength, 4),
                }
            )

        if strong_refute_override:
            det_label = "Hallucination"
        elif not strong_evidence_seen or (support + refute) <= 1e-8:
            det_label = "Uncertain"
        elif refute <= 1e-9 and support >= 0.25 and high_trust_support_count >= 1:
            # Strictness fix: non-trivial support with no contradiction should pass as verified.
            det_label = "Verified"
        elif support > tuning["verify_ratio"] * refute:
            if (
                len(strong_support_domains) >= 2
                or high_trust_support_count >= 2
                or authoritative_support_count >= 1
                or (high_trust_support_count >= 1 and support >= tuning["verified_support_floor"])
                or constraint_sig > 0
            ):
                det_label = "Verified"
            else:
                det_label = "Uncertain"
        elif refute > tuning["hallucination_ratio"] * support:
            det_label = "Hallucination"
        else:
            det_label = "Conflicting"

        # Phase rule: technical + no direct evidence => uncertain.
        if (
            is_technical
            and direct_support_count == 0
            and high_trust_support_count < 1
            and authoritative_support_count < 1
            and support < 1.2
            and det_label == "Verified"
        ):
            det_label = "Uncertain"

        # Phase rule: only low reliability support cannot be verified.
        if det_label == "Verified" and high_trust_support_count == 0:
            det_label = "Uncertain"

        # Medical guardrails.
        if is_medical:
            if contradiction_exists and support > 0 and refute > 0:
                det_label = "Conflicting"
            if det_label == "Verified" and not (high_trust_support_count >= 2 or authoritative_support_count >= 1):
                det_label = "Uncertain"

        if det_label == "Verified":
            status = "Verified"
            confidence = min(1.0, 0.55 + 0.45 * (support / max(1e-6, support + refute)))
            score = min(1.0, 0.7 + 0.3 * (support / max(1e-6, support + refute)))
        elif det_label == "Hallucination":
            status = "Hallucination"
            confidence = min(1.0, 0.55 + 0.45 * (refute / max(1e-6, support + refute)))
            score = max(0.0, 0.3 * (support / max(1e-6, support + refute)))
        else:
            status = "Plausible"
            confidence = 0.35 if det_label == "Conflicting" else 0.25
            score = 0.5

        # Phase rule: safety-critical low confidence => uncertain with warning.
        if is_safety and confidence < 0.7 and status != "Hallucination":
            status = "Plausible"
            det_label = "Uncertain"
            warning = "Safety-critical claim with confidence < 0.7; downgraded to Uncertain."
            confidence = min(confidence, 0.69)
            score = 0.5

        return {
            "status": status,
            "confidence": round(float(confidence), 4),
            "reasoning": (
                f"Deterministic rule: relation={relation}, support={support:.3f}, refute={refute:.3f}, "
                f"strong_sources={len(strong_support_domains)}, label={det_label}."
            ),
            "score": round(float(score), 4),
            "metadata": {
                "deterministic_label": det_label,
                "support": round(float(support), 4),
                "refute": round(float(refute), 4),
                "relation": relation,
                "strong_support_sources": sorted(strong_support_domains),
                "strong_refute_override": strong_refute_override,
                "is_technical": is_technical,
                "is_medical": is_medical,
                "is_safety_critical": is_safety,
                "high_trust_support_count": high_trust_support_count,
                "authoritative_support_count": authoritative_support_count,
                "direct_support_count": direct_support_count,
                "contradiction_exists": contradiction_exists,
                "constraint_signal": constraint_sig,
                "constraint_name": constraint_name,
                "warning": warning,
                "tuning": tuning,
                "per_evidence": per_evidence[:12],
            },
        }


deterministic_voter = DeterministicVoter()
