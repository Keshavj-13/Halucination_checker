from typing import List, Dict, Any
from services.voters.base import Voter
from models.schemas import Evidence

class HeuristicVoter(Voter):
    """Simple keyword overlap voter."""
    
    async def vote(self, claim: str, evidence: List[Evidence]) -> Dict[str, Any]:
        claim_words = set(claim.lower().split())
        all_ev_words = set(" ".join([ev.snippet for ev in evidence]).lower().split())
        
        if not claim_words: return {"status": "Plausible", "confidence": 0.5, "reasoning": "Empty claim."}
        
        intersection = claim_words.intersection(all_ev_words)
        overlap = len(intersection) / len(claim_words)
        
        if overlap > 0.7:
            status = "Verified"
        elif overlap > 0.3:
            status = "Plausible"
        else:
            status = "Hallucination"
            
        return {
            "status": status,
            "confidence": round(overlap, 2),
            "reasoning": f"Keyword overlap: {int(overlap*100)}%"
        }

heuristic_voter = HeuristicVoter()
