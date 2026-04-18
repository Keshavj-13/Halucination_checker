from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class Evidence(BaseModel):
    title: str
    snippet: str
    url: str
    support: str # "supporting", "contradicting", "weak"
    reliability_score: float = 0.0 # 0.0 to 1.0

class Claim(BaseModel):
    text: str
    status: str # "Verified", "Plausible", "Hallucination"
    confidence: float
    evidence: List[Evidence]
    start_idx: int = 0
    end_idx: int = 0
    voter_scores: Dict[str, float] = {} # Individual scores from each voter

class AuditRequest(BaseModel):
    document: str

class AuditResponse(BaseModel):
    document: str
    total: int
    verified: int
    plausible: int
    hallucinations: int
    claims: List[Claim]
