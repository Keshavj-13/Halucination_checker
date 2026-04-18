import httpx
import logging
import os
from typing import List, Dict, Any
from services.voters.base import Voter
from models.schemas import Evidence

logger = logging.getLogger("audit-api.voters.semantic")

class SemanticVoter(Voter):
    """Uses local Ollama embeddings to check semantic similarity."""
    
    def __init__(self):
        self.base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").replace("/v1", "/api/embeddings")
        self.model = "nomic-embed-text"

    async def _get_embedding(self, text: str) -> List[float]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    "http://localhost:11434/api/embeddings",
                    json={"model": self.model, "prompt": text}
                )
                response.raise_for_status()
                return response.json()["embedding"]
        except Exception as e:
            logger.error(f"Embedding failed: {str(e)}")
            return []

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2: return 0.0
        dot = sum(a*b for a,b in zip(v1, v2))
        norm1 = sum(a*a for a in v1)**0.5
        norm2 = sum(a*a for a in v2)**0.5
        return dot / (norm1 * norm2) if norm1 and norm2 else 0.0

    async def vote(self, claim: str, evidence: List[Evidence]) -> Dict[str, Any]:
        claim_emb = await self._get_embedding(claim)
        if not claim_emb:
            return {"status": "Plausible", "confidence": 0.5, "reasoning": "Semantic check skipped (Ollama error)."}
            
        best_sim = 0.0
        for ev in evidence:
            ev_emb = await self._get_embedding(ev.snippet)
            sim = self._cosine_similarity(claim_emb, ev_emb)
            best_sim = max(best_sim, sim)
            
        if best_sim > 0.85:
            return {"status": "Verified", "confidence": best_sim, "reasoning": "High semantic similarity."}
        elif best_sim > 0.6:
            return {"status": "Plausible", "confidence": best_sim, "reasoning": "Moderate semantic overlap."}
        else:
            return {"status": "Hallucination", "confidence": 0.8, "reasoning": "Low semantic similarity to evidence."}

semantic_voter = SemanticVoter()
