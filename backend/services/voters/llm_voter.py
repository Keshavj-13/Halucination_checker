from typing import List, Dict, Any
from services.voters.base import Voter
from models.schemas import Evidence
from services.llm_client import llm

class LLMVoter(Voter):
    """Gemini expert voter (20% weight)."""
    
    async def vote(self, claim: str, evidence: List[Evidence]) -> Dict[str, Any]:
        context = "\n".join([f"[{i}] {ev.snippet}" for i, ev in enumerate(evidence)])
        prompt = f"Verify this claim using the context.\nContext: {context}\nClaim: {claim}"
        
        try:
            response = await llm.chat(prompt, system_prompt="Verify claim. Output ONLY JSON: {'status': 'Verified'|'Plausible'|'Hallucination', 'confidence': 0.0-1.0, 'reasoning': '...'}")
            data = llm.parse_json(response)
            return {
                "status": data.get("status", "Plausible"),
                "confidence": data.get("confidence", 0.5),
                "reasoning": data.get("reasoning", "LLM analysis complete.")
            }
        except Exception as e:
            return {"status": "Plausible", "confidence": 0.0, "reasoning": f"LLM failed: {str(e)}"}

llm_voter = LLMVoter()
