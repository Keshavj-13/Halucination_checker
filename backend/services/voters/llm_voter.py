from typing import List, Dict, Any
from services.voters.base import Voter
from models.schemas import Evidence
from services.llm_client import llm
from services.config import LLM_VOTER_ENABLED


class LLMVoter(Voter):
    """External LLM voter used as a weak signal only."""

    @staticmethod
    def _normalize_status(value: str) -> str:
        v = (value or "").strip().lower()
        if v in {"verified", "support", "supported", "entails"}:
            return "Verified"
        if v in {"hallucination", "refuted", "refute", "contradiction", "contradicted"}:
            return "Hallucination"
        return "Plausible"

    async def vote(self, claim: str, evidence: List[Evidence]) -> Dict[str, Any]:
        if not LLM_VOTER_ENABLED:
            return {
                "status": "Plausible",
                "confidence": 0.2,
                "reasoning": "LLM voter disabled for speed profile.",
                "score": 0.2,
            }

        if not evidence:
            return {"status": "Plausible", "confidence": 0.2, "reasoning": "No evidence provided to LLM.", "score": 0.2}

        top_evidence = evidence[:4]
        context = "\n".join([f"[{i}] ({ev.url}) {ev.snippet[:500]}" for i, ev in enumerate(top_evidence)])
        prompt = (
            "You are a fact-checking assistant.\n"
            "Task: Classify whether claim is supported, refuted, or uncertain using ONLY the evidence.\n"
            "Return JSON with keys: status, confidence, reasoning.\n"
            f"Claim: {claim}\n"
            f"Evidence:\n{context}"
        )

        try:
            response = await llm.chat(
                prompt,
                system_prompt=(
                    "Output ONLY JSON. status must be one of supported/refuted/uncertain. "
                    "confidence must be 0..1 and conservative."
                ),
            )
            data = llm.parse_json(response)
            status = self._normalize_status(data.get("status", "uncertain"))
            conf = float(data.get("confidence", 0.5))
            # Keep this voter weak by bounding max impact.
            bounded_conf = max(0.05, min(conf, 0.75))
            return {
                "status": status,
                "confidence": bounded_conf,
                "reasoning": data.get("reasoning", "LLM analysis complete."),
                "score": bounded_conf,
            }
        except Exception as e:
            return {
                "status": "Plausible",
                "confidence": 0.1,
                "reasoning": f"LLM failed: {str(e)}",
                "score": 0.1,
            }

llm_voter = LLMVoter()
