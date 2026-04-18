import logging
import re
from typing import List, Set
from models.schemas import Claim, Evidence
from duckduckgo_search import DDGS

logger = logging.getLogger("audit-api.heuristic")

class HeuristicVerifier:
    """
    Layer 1: Fast, local text overlap and entity matching.
    """
    
    def _extract_entities(self, text: str) -> Set[str]:
        """Simple regex-based entity extraction (Capitalized words, numbers)."""
        # Find capitalized words (Proper Nouns) and numbers
        entities = set(re.findall(r"\b[A-Z][a-z]+\b|\b\d+(?:\.\d+)?\b", text))
        return entities

    def _calculate_overlap(self, claim: str, snippet: str) -> float:
        claim_words = set(claim.lower().split())
        snippet_words = set(snippet.lower().split())
        if not claim_words: return 0.0
        intersection = claim_words.intersection(snippet_words)
        
        # Entity matching boost
        claim_entities = self._extract_entities(claim)
        snippet_entities = self._extract_entities(snippet)
        entity_matches = claim_entities.intersection(snippet_entities)
        
        entity_score = len(entity_matches) / len(claim_entities) if claim_entities else 0.0
        word_score = len(intersection) / len(claim_words)
        
        # Weighted score: entities are more important
        return (word_score * 0.4) + (entity_score * 0.6)

    async def verify(self, text: str) -> Claim:
        logger.info(f"Heuristic verification (Layer 1): {text[:50]}...")
        
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(text, max_results=3))
            
            if not results:
                return Claim(text=text, status="Plausible", confidence=0.3, evidence=[])
            
            best_overlap = 0.0
            evidence_list = []
            for res in results:
                snippet = res.get("body", "")
                overlap = self._calculate_overlap(text, snippet)
                evidence = Evidence(
                    title=res.get("title", "Web Source"),
                    snippet=snippet,
                    url=res.get("href", "#"),
                    support="supporting" if overlap > 0.3 else "weak"
                )
                evidence_list.append(evidence)
                best_overlap = max(best_overlap, overlap)
            
            if best_overlap > 0.6:
                status = "Verified"
            elif best_overlap > 0.2:
                status = "Plausible"
            else:
                status = "Hallucination"
                
            return Claim(
                text=text,
                status=status,
                confidence=round(best_overlap, 2),
                evidence=evidence_list[:2]
            )
        except Exception as e:
            logger.error(f"Heuristic failed: {str(e)}")
            return Claim(text=text, status="Plausible", confidence=0.0, evidence=[])

heuristic_verifier = HeuristicVerifier()
