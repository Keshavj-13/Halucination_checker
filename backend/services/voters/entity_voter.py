import re
from typing import List, Dict, Any, Set
from services.voters.base import Voter
from models.schemas import Evidence

class EntityVoter(Voter):
    """Checks for strict matches of names, dates, and numbers."""
    
    def _extract_entities(self, text: str) -> Set[str]:
        # Proper nouns and numbers
        return set(re.findall(r"\b[A-Z][a-z]+\b|\b\d+(?:\.\d+)?\b", text))

    async def vote(self, claim: str, evidence: List[Evidence]) -> Dict[str, Any]:
        claim_entities = self._extract_entities(claim)
        if not claim_entities:
            return {"status": "Plausible", "confidence": 0.5, "reasoning": "No entities found to verify."}
            
        all_evidence_text = " ".join([ev.snippet for ev in evidence])
        evidence_entities = self._extract_entities(all_evidence_text)
        
        matches = claim_entities.intersection(evidence_entities)
        match_ratio = len(matches) / len(claim_entities)
        
        if match_ratio > 0.8:
            return {"status": "Verified", "confidence": match_ratio, "reasoning": f"Matched entities: {', '.join(matches)}"}
        elif match_ratio > 0.3:
            return {"status": "Plausible", "confidence": match_ratio, "reasoning": f"Partial entity match: {', '.join(matches)}"}
        else:
            return {"status": "Hallucination", "confidence": 0.7, "reasoning": "Major entities missing from evidence."}

entity_voter = EntityVoter()
