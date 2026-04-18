import logging
from typing import List
from services.llm_client import llm

logger = logging.getLogger("audit-api.extractor")

SYSTEM_PROMPT = """
You are an expert editor. Extract individual, atomic, and verifiable claims from the document.
Output ONLY a JSON list of strings.

Examples:
Input: "The Earth is round and it orbits the Sun."
Output: ["The Earth is round", "The Earth orbits the Sun"]

Input: "Python is popular but slow."
Output: ["Python is popular", "Python is slow"]

Input: "The 2024 Olympics will be held in Paris, which is the capital of France."
Output: ["The 2024 Olympics will be held in Paris", "Paris is the capital of France"]
"""

async def extract_claims(document: str) -> List[str]:
    """Use LLM to extract atomic claims with few-shot guidance."""
    logger.info("Extracting atomic claims using LLM (Few-Shot)...")
    
    prompt = f"Extract atomic claims from this document:\n\n{document}"
    
    try:
        response = await llm.chat(prompt, system_prompt=SYSTEM_PROMPT)
        claims = llm.parse_json(response)
        
        if isinstance(claims, list):
            # Clean up and filter
            cleaned = [str(c).strip() for c in claims if len(str(c).strip()) > 5]
            logger.info(f"Successfully extracted {len(cleaned)} atomic claims")
            return cleaned
        return []
    except Exception as e:
        logger.error(f"LLM Extraction failed: {str(e)}. Falling back to regex.")
        import re
        sentences = re.split(r'(?<=[.!?])\s+', document.strip())
        return [s.strip() for s in sentences if len(s.strip()) > 10]
