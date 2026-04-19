from typing import List, Dict, Any
import re
import numpy as np
from services.voters.base import Voter
from models.schemas import Evidence
from services.embedding_service import embedding_service


class SemanticVoter(Voter):
    """Uses local Ollama embeddings to check semantic similarity."""

    def __init__(self):
        pass

    async def _get_embedding(self, text: str) -> List[float]:
        return await embedding_service.embed_text(text)

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2:
            return 0.0
        a = np.asarray(v1, dtype=np.float32)
        b = np.asarray(v2, dtype=np.float32)
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom <= 1e-8:
            return 0.0
        return float(np.dot(a, b) / denom)

    def _fallback_similarity(self, claim: str, snippet: str) -> float:
        c = set(re.findall(r"\w+", claim.lower()))
        s = set(re.findall(r"\w+", snippet.lower()))
        union = len(c | s)
        return (len(c & s) / union) if union else 0.0

    async def vote(self, claim: str, evidence: List[Evidence]) -> Dict[str, Any]:
        if not evidence:
            return {"status": "Hallucination", "confidence": 0.1, "reasoning": "No evidence available.", "score": 0.1}

        claim_emb = await self._get_embedding(claim)

        evidence_embeddings = []
        if claim_emb:
            missing = [i for i, ev in enumerate(evidence) if not ev.embedding]
            if missing:
                missing_texts = [evidence[i].snippet for i in missing]
                missing_embs = await embedding_service.embed_many(missing_texts)
                for idx, emb in zip(missing, missing_embs):
                    evidence[idx].embedding = emb
            evidence_embeddings = [ev.embedding or [] for ev in evidence]

        best_sim = 0.0
        best_idx = 0
        for idx, ev in enumerate(evidence):
            if claim_emb and idx < len(evidence_embeddings):
                sim = self._cosine_similarity(claim_emb, evidence_embeddings[idx])
            else:
                sim = self._fallback_similarity(claim, ev.snippet)

            sim *= (0.7 + 0.3 * ev.reliability_score)
            best_sim = max(best_sim, sim)
            if sim == best_sim:
                best_idx = idx

        if best_sim > 0.82:
            return {"status": "Verified", "confidence": best_sim, "reasoning": "High semantic similarity.", "score": best_sim, "metadata": {"top_evidence_idx": best_idx}}
        elif best_sim > 0.56:
            return {"status": "Plausible", "confidence": best_sim, "reasoning": "Moderate semantic overlap.", "score": best_sim, "metadata": {"top_evidence_idx": best_idx}}
        else:
            return {"status": "Hallucination", "confidence": 1.0 - best_sim, "reasoning": "Low semantic similarity to evidence.", "score": best_sim, "metadata": {"top_evidence_idx": best_idx}}

semantic_voter = SemanticVoter()
