import re
import logging
from typing import List, Tuple
from services.llm_client import llm
import os

logger = logging.getLogger("audit-api.extractor")

USE_LLM_EXTRACTION = os.getenv("USE_LLM_EXTRACTION", "false").lower() == "true"

async def extract_claims(document: str) -> List[dict]:
    """
    Extracts claims with character indices.
    Returns a list of dicts: {"text": str, "start": int, "end": int}
    """
    if USE_LLM_EXTRACTION:
        return await _extract_with_llm(document)
    return _extract_with_rules(document)

def _extract_with_rules(document: str) -> List[dict]:
    """Rule-based sentence splitting with index tracking."""
    logger.info("Extracting claims using rule-based splitter...")
    
    # Simple sentence splitting regex
    pattern = r'[^.!?]+[.!?]'
    matches = re.finditer(pattern, document)
    
    claims = []
    for match in matches:
        text = match.group().strip()
        if len(text) > 15: # Filter out very short fragments
            claims.append({
                "text": text,
                "start": match.start(),
                "end": match.end()
            })
    
    # If no sentences found, return the whole thing as one claim
    if not claims and document.strip():
        claims.append({
            "text": document.strip(),
            "start": 0,
            "end": len(document)
        })
        
    return claims

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
