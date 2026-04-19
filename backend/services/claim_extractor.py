import re
import logging
from typing import List
from services.llm_client import llm
import os
import time
from services.telemetry import telemetry

logger = logging.getLogger("audit-api.extractor")

USE_LLM_EXTRACTION = os.getenv("USE_LLM_EXTRACTION", "false").lower() == "true"
CLAIM_ATOMIC_SPLIT_ENABLED = os.getenv("CLAIM_ATOMIC_SPLIT_ENABLED", "false").lower() == "true"

async def extract_claims(document: str) -> List[dict]:
    """
    Extracts claims with character indices.
    Returns a list of dicts: {"text": str, "start": int, "end": int}
    """
    started = time.perf_counter()
    if USE_LLM_EXTRACTION:
        claims = await _extract_with_llm(document)
    else:
        claims = _extract_with_rules(document)

    telemetry.event(
        "extract_done",
        stage="extract",
        message=f"extracted {len(claims)} claims",
        payload={"num_claims": len(claims), "runtime_ms": round((time.perf_counter() - started) * 1000.0, 2), "mode": "llm" if USE_LLM_EXTRACTION else "rules"},
    )
    return claims

def _extract_with_rules(document: str) -> List[dict]:
    """Rule-based sentence splitting with index tracking and atomic decomposition."""
    logger.info("Extracting claims using rule-based splitter...")

    pattern = r"[^.!?]+[.!?]"
    matches = re.finditer(pattern, document)

    claims = []
    for match in matches:
        sentence_text = match.group().strip()
        if len(sentence_text) <= 8:
            continue

        sentence_start = match.start()
        parts = _split_atomic(sentence_text) if CLAIM_ATOMIC_SPLIT_ENABLED else [sentence_text]
        cursor = 0
        for part in parts:
            normalized = part.strip()
            if len(normalized) <= 12:
                continue

            local_idx = sentence_text.find(normalized, cursor)
            if local_idx < 0:
                local_idx = sentence_text.find(normalized)
            if local_idx < 0:
                continue
            cursor = local_idx + len(normalized)

            start = sentence_start + local_idx
            end = start + len(normalized)
            claims.append({"text": normalized, "start": start, "end": end})

    # If no sentences found, return whole document as single claim
    if not claims and document.strip():
        claims.append({
            "text": document.strip(),
            "start": 0,
            "end": len(document)
        })

    return claims


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

    # Basic conjunction splits with subject carry-over support.
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

async def _extract_with_llm(document: str) -> List[dict]:
    """LLM-based extraction (Simplified for Gemini)."""
    logger.info("Extracting claims using Gemini...")
    prompt = f"Extract atomic claims from this document. Output ONLY a JSON list of strings: {document}"
    
    try:
        response = await llm.chat(prompt, system_prompt="Extract claims. Output ONLY JSON list.")
        texts = llm.parse_json(response)
        
        # Map texts back to indices (heuristic mapping)
        claims = []
        for text in texts:
            start = document.find(text)
            if start != -1:
                claims.append({
                    "text": text,
                    "start": start,
                    "end": start + len(text)
                })
        return claims
    except Exception as e:
        logger.error(f"LLM Extraction failed, falling back to rules: {str(e)}")
        return _extract_with_rules(document)
