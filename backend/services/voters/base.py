from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from models.schemas import Evidence

class Voter(ABC):
    @abstractmethod
    async def vote(self, claim: str, evidence: List[Evidence]) -> Dict[str, Any]:
        """
        Returns a dict: {"status": str, "confidence": float, "reasoning": str}
        """
        pass
