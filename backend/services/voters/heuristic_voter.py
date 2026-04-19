from typing import List, Dict, Any
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from services.voters.base import Voter
from models.schemas import Evidence


class HeuristicVoter(Voter):
    """TF-IDF weighted lexical overlap voter."""

    def __init__(self):
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")

    async def vote(self, claim: str, evidence: List[Evidence]) -> Dict[str, Any]:
        if not claim.strip():
            return {"status": "Plausible", "confidence": 0.5, "reasoning": "Empty claim.", "score": 0.5}

        if not evidence:
            return {"status": "Hallucination", "confidence": 0.1, "reasoning": "No evidence available.", "score": 0.1}

        best_score = 0.0
        best_idx = 0

        for idx, ev in enumerate(evidence):
            snippet = ev.snippet.strip()
            if not snippet:
                continue

            try:
                tfidf = self.vectorizer.fit_transform([claim, snippet])
                sim = float((tfidf[0] @ tfidf[1].T).toarray()[0][0])
            except ValueError:
                sim = 0.0

            # Reliability-weighted lexical score
            stance = (ev.stance or "mention").lower()
            stance_mult = 1.0 if stance == "support" else 0.65 if stance == "neutral" else 0.35
            weighted = sim * (0.7 + 0.3 * ev.reliability_score) * stance_mult * (1.0 - min(max(ev.bias_penalty, 0.0), 1.0) * 0.25)
            if weighted > best_score:
                best_score = weighted
                best_idx = idx

        if best_score >= 0.62:
            status = "Verified"
        elif best_score >= 0.34:
            status = "Plausible"
        else:
            status = "Hallucination"

        top_url = evidence[best_idx].url if evidence else ""
        return {
            "status": status,
            "confidence": round(float(best_score), 4),
            "reasoning": f"Best TF-IDF overlap={best_score:.2f} from {top_url}",
            "score": round(float(best_score), 4),
            "metadata": {"top_evidence_idx": best_idx},
        }


heuristic_voter = HeuristicVoter()
