import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from services.telemetry import telemetry

try:
    import spacy
except Exception:  # pragma: no cover
    spacy = None

logger = logging.getLogger("audit-api.extractor")

CLAIM_ATOMIC_SPLIT_ENABLED = os.getenv("CLAIM_ATOMIC_SPLIT_ENABLED", "false").lower() == "true"

_NLP = None


def _get_nlp():
    global _NLP
    if _NLP is not None:
        return _NLP

    if spacy is None:  # pragma: no cover
        _NLP = None
        return _NLP

    try:
        _NLP = spacy.load("en_core_web_sm", disable=["lemmatizer"])
    except Exception:
        nlp = spacy.blank("en")
        if "sentencizer" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer")
        _NLP = nlp
    return _NLP

async def extract_claims(document: str) -> List[dict]:
    """
    Extracts claims with character indices.
    Returns a list of dicts: {"text": str, "start": int, "end": int}
    """
    started = time.perf_counter()
    claims = _extract_with_rules(document)

    telemetry.event(
        "extract_done",
        stage="extract",
        message=f"extracted {len(claims)} claims",
        payload={"num_claims": len(claims), "runtime_ms": round((time.perf_counter() - started) * 1000.0, 2), "mode": "structured_rules"},
    )
    return claims

def _extract_with_rules(document: str) -> List[dict]:
    """Deterministic structured extraction with spaCy-first parsing and stable offsets."""
    logger.info("Extracting claims using structured deterministic parser...")

    text = (document or "").strip()
    if not text:
        return []

    nlp = _get_nlp()
    claims: List[Dict[str, Any]] = []

    if nlp is None:
        return _fallback_regex_claims(text)

    doc = nlp(text)
    for sent in doc.sents:
        sent_text = sent.text.strip()
        if len(sent_text) <= 8:
            continue

        parts = _split_atomic(sent_text) if CLAIM_ATOMIC_SPLIT_ENABLED else [sent_text]
        cursor = sent.start_char
        for part in parts:
            normalized = part.strip()
            if len(normalized) <= 12:
                continue
            local_idx = text.find(normalized, cursor)
            if local_idx < 0:
                local_idx = text.find(normalized)
            if local_idx < 0:
                continue
            cursor = local_idx + len(normalized)

            structured = _build_structured_claim(normalized, nlp)
            claims.append(
                {
                    "text": normalized,
                    "start": local_idx,
                    "end": local_idx + len(normalized),
                    "structured_claim": structured,
                    "claim_type": structured.get("claim_type", "UNVERIFIABLE"),
                    "parse_confidence": structured.get("parse_confidence", 0.0),
                }
            )

    if not claims:
        fallback = _build_structured_claim(text, nlp)
        claims.append(
            {
                "text": text,
                "start": 0,
                "end": len(text),
                "structured_claim": fallback,
                "claim_type": fallback.get("claim_type", "UNVERIFIABLE"),
                "parse_confidence": fallback.get("parse_confidence", 0.0),
            }
        )

    return claims


def _fallback_regex_claims(text: str) -> List[dict]:
    pattern = r"[^.!?]+[.!?]?"
    out: List[dict] = []
    for match in re.finditer(pattern, text):
        sent = match.group().strip()
        if len(sent) <= 12:
            continue
        structured = _build_structured_claim(sent, nlp=None)
        out.append(
            {
                "text": sent,
                "start": match.start(),
                "end": match.start() + len(sent),
                "structured_claim": structured,
                "claim_type": structured.get("claim_type", "UNVERIFIABLE"),
                "parse_confidence": structured.get("parse_confidence", 0.0),
            }
        )
    return out


def _split_atomic(sentence: str) -> List[str]:
    """
    Split compound factual statements into atomic units while keeping meaning.
    Ex: "Tesla was founded in 2003 and is headquartered in Texas."
    -> ["Tesla was founded in 2003.", "Tesla is headquartered in Texas."]
    """
    cleaned = sentence.strip()
    if not cleaned:
        return []

    # Normalize trailing punctuation once
    trailing = "." if cleaned[-1] not in ".!?" else cleaned[-1]
    cleaned = cleaned.rstrip(".!? ")

    # Deterministic conjunction split only as a secondary pass after sentence parsing.
    segments = re.split(r"\s+(?:and|but|while|whereas)\s+", cleaned)
    if len(segments) == 1:
        return [cleaned + trailing]

    atomic = []
    for idx, seg in enumerate(segments):
        seg = seg.strip()
        if not seg:
            continue
        # Keep exact fragment text for offset mapping; only last segment keeps sentence punctuation.
        if idx == len(segments) - 1:
            atomic.append(seg + trailing)
        else:
            atomic.append(seg)

    return atomic


def _build_structured_claim(text: str, nlp=None) -> Dict[str, Any]:
    doc = nlp(text) if nlp is not None else None
    lowered = text.lower()
    negation = bool(re.search(r"\b(not|never|no|none|without|cannot|can't|isn't|aren't|won't|didn't)\b", lowered))

    subject = ""
    predicate = ""
    obj = ""
    entity_types: List[str] = []
    parse_conf = 0.45

    if doc is not None:
        ents = getattr(doc, "ents", [])
        entity_types = sorted({e.label_ for e in ents if e.label_})

        root = None
        for token in doc:
            if token.dep_ == "ROOT":
                root = token
                break

        if root is not None:
            predicate = root.lemma_ or root.text
            parse_conf = 0.72
            for token in doc:
                if token.dep_ in {"nsubj", "nsubjpass"}:
                    subject = token.text if not token.subtree else " ".join(t.text for t in token.subtree)
                    break
            for token in doc:
                if token.dep_ in {"dobj", "pobj", "attr", "oprd"}:
                    obj = token.text if not token.subtree else " ".join(t.text for t in token.subtree)
                    break

    if not subject:
        parts = re.split(r"\b(is|are|was|were|has|have|had|can|could|will|would)\b", text, maxsplit=1, flags=re.IGNORECASE)
        if parts:
            subject = parts[0].strip()[:120]
    if not predicate:
        m = re.search(r"\b(is|are|was|were|has|have|had|can|could|will|would|causes?|includes?|contains?)\b", lowered)
        predicate = m.group(1) if m else "states"
    if not obj:
        obj = text[:220]

    claim_type = _infer_claim_type(text)
    canonical_predicate = _canonicalize_predicate(predicate)
    numeric_value, numeric_unit = _extract_numeric(text)

    return {
        "subject": subject.strip(),
        "predicate": predicate.strip(),
        "canonical_predicate": canonical_predicate,
        "object": obj.strip(),
        "claim_type": claim_type,
        "negation": negation,
        "numeric_value": numeric_value,
        "numeric_unit": numeric_unit,
        "source_sentence": text,
        "entity_types": entity_types,
        "parse_confidence": round(parse_conf, 4),
    }


def _canonicalize_predicate(predicate: str) -> str:
    p = (predicate or "").lower().strip()
    mapping = {
        "is": "be",
        "are": "be",
        "was": "be",
        "were": "be",
        "has": "have",
        "had": "have",
        "causes": "cause",
        "contains": "contain",
        "includes": "include",
    }
    return mapping.get(p, p or "state")


def _extract_numeric(text: str) -> tuple[Optional[float], Optional[str]]:
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*([a-zA-Z%/]+)?\b", text)
    if not m:
        return None, None
    try:
        return float(m.group(1)), (m.group(2) or "").lower() or None
    except Exception:
        return None, None


def _infer_claim_type(text: str) -> str:
    t = (text or "").lower()
    if re.search(r"\b(i think|i feel|best|worst|beautiful|ugly|should|opinion|prefer)\b", t):
        return "SUBJECTIVE"
    if re.search(r"\b\d+(?:\.\d+)?\s*(km|m|kg|g|mile|miles|%|percent|c|f|k|years?|days?)\b", t):
        return "NUMERIC_CLAIM"
    if re.search(r"\b(19|20)\d{2}\b|\bon\s+\w+\s+\d{1,2},?\s+(19|20)\d{2}\b", t):
        return "DATE_CLAIM"
    if re.search(r"\b(before|after|during|then|earlier|later|timeline)\b", t):
        return "TEMPORAL"
    if re.search(r"\b(defines?|means?|is called|refers to)\b", t):
        return "DEFINITION"
    if re.search(r"\b(trial|study|experiment|clinical|efficacy|physics|biology|chemistry)\b", t):
        return "SCIENTIFIC"
    if re.search(r"\b(is|are|has|have|born|died|capital|population|located|orbits|contains)\b", t):
        return "ENTITY_RELATION"
    return "UNVERIFIABLE"
