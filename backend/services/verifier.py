import logging
import json
from typing import List
from models.schemas import Claim, Evidence
from services.llm_client import llm
from services.search_service import search_service

logger = logging.getLogger("audit-api.verifier")

QUERY_GEN_PROMPT = """
Generate a single, concise search query to verify the following claim.
Output ONLY the query string.

Example:
Claim: "The human brain has 86 billion neurons."
Query: "human brain neuron count 86 billion"
"""

VERIFIER_PROMPT = """
You are a professional fact-checker. Verify the claim using ONLY the provided context snippets.
If the context doesn't mention the claim, use your knowledge but lower the confidence and set status to "Plausible".

Output ONLY a JSON object:
{
  "status": "Verified" | "Plausible" | "Hallucination",
  "confidence": 0.0 to 1.0,
  "reasoning": "Brief explanation",
  "evidence_indices": [0, 1]
}

Example:
Context: [0] "Earth orbits Sun at 93m miles."
Claim: "Earth is 93 million miles from the Sun."
Output: {"status": "Verified", "confidence": 0.98, "reasoning": "Context explicitly confirms the distance.", "evidence_indices": [0]}
"""

async def verify_claim(text: str) -> Claim:
    """Search-Augmented Verification flow."""
    logger.info(f"Verifying claim: {text[:50]}...")
    
    try:
        # 1. Generate Query
        query = await llm.chat(f"Claim: {text}", system_prompt=QUERY_GEN_PROMPT)
        query = query.strip().strip('"')
        
        # 2. Search
        evidence_pool = await search_service.search(query)
        context_str = "\n".join([f"[{i}] {ev.snippet}" for i, ev in enumerate(evidence_pool)])
        
        # 3. Verify
        prompt = f"Context:\n{context_str}\n\nClaim: {text}"
        response = await llm.chat(prompt, system_prompt=VERIFIER_PROMPT)
        data = llm.parse_json(response)
        
        # 4. Map back to Evidence objects
        indices = data.get("evidence_indices", [])
        selected_evidence = []
        for idx in indices:
            if 0 <= idx < len(evidence_pool):
                selected_evidence.append(evidence_pool[idx])
        
        # If no evidence selected but status is Verified/Plausible, add at least one
        if not selected_evidence and evidence_pool:
            selected_evidence = [evidence_pool[0]]

        return Claim(
            text=text,
            status=data.get("status", "Plausible"),
            confidence=data.get("confidence", 0.5),
            evidence=selected_evidence
        )
        
    except Exception as e:
        logger.error(f"Verification failed for '{text[:30]}': {str(e)}")
        return Claim(
            text=text,
            status="Plausible",
            confidence=0.4,
            evidence=[Evidence(title="Search Error", snippet="Could not verify via search.", url="#", support="weak")]
        )

async def verify_claims(claims: List[str]) -> List[Claim]:
    results = []
    for claim in claims:
        results.append(await verify_claim(claim))
    return results
