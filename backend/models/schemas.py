from pydantic import BaseModel
from typing import List, Literal


class Evidence(BaseModel):
    title: str
    snippet: str
    url: str
    support: Literal["supporting", "weak"]


class Claim(BaseModel):
    text: str
    status: Literal["Verified", "Plausible", "Hallucination"]
    confidence: float
    evidence: List[Evidence]


class AuditRequest(BaseModel):
    document: str


class AuditResponse(BaseModel):
    claims: List[Claim]
    total: int
    verified: int
    plausible: int
    hallucinations: int
