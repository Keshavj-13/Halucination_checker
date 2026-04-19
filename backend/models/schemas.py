from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class EvidenceChunk(BaseModel):
    text: str
    start_char: int = 0
    end_char: int = 0
    token_count: int = 0
    embedding: Optional[List[float]] = None


class Evidence(BaseModel):
    title: str
    snippet: str
    url: str
    support: str  # "supporting", "contradicting", "weak"
    stance: str = "mention"  # support|refute|neutral|mention|quotation|reported_belief
    attribution: str = "none"  # none|authoritative|reported|quoted
    citation_direction: str = "none"  # endorses|refutes|reports|none
    reliability_score: float = 0.0  # 0.0 to 1.0
    reliability_explanation: str = ""
    source_domain: str = ""
    published_at: Optional[str] = None
    chunk_start: int = 0
    chunk_end: int = 0
    embedding: Optional[List[float]] = None
    cluster_id: Optional[int] = None
    bias_penalty: float = 0.0
    sponsorship_flag: bool = False
    is_quote: bool = False
    is_reported_belief: bool = False
    page_quality_signals: Dict[str, float] = Field(default_factory=dict)


class VoterResult(BaseModel):
    status: str
    confidence: float
    reasoning: str
    score: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RuntimeMetadata(BaseModel):
    total_runtime_ms: float = 0.0
    retrieval_runtime_ms: float = 0.0
    voting_runtime_ms: float = 0.0
    num_urls: int = 0
    num_chunks: int = 0
    cache_hits: int = 0
    external_failures: List[str] = Field(default_factory=list)


class Claim(BaseModel):
    text: str
    status: str  # "Verified", "Plausible", "Hallucination"
    confidence: float
    evidence: List[Evidence]
    start_idx: int = 0
    end_idx: int = 0
    voter_scores: Dict[str, float] = Field(default_factory=dict)
    voter_results: Dict[str, VoterResult] = Field(default_factory=dict)
    final_score: float = 0.0
    label: str = "Plausible"
    best_evidence: List[Evidence] = Field(default_factory=list)
    contradicting_evidence: List[Evidence] = Field(default_factory=list)
    source_reliability_explanation: str = ""
    runtime: RuntimeMetadata = Field(default_factory=RuntimeMetadata)


class ClaimLogRecord(BaseModel):
    document_id: str
    claim_text: str
    start_idx: int
    end_idx: int
    retrieved_urls: List[str] = Field(default_factory=list)
    evidence_chunks: List[Evidence] = Field(default_factory=list)
    chunk_stances: List[str] = Field(default_factory=list)
    source_reliability_scores: List[float] = Field(default_factory=list)
    bias_scores: List[float] = Field(default_factory=list)
    voter_scores: Dict[str, float] = Field(default_factory=dict)
    voter_results: Dict[str, Any] = Field(default_factory=dict)
    final_consensus_score: float
    final_label: str
    confidence: float
    runtime_metadata: Dict[str, Any] = Field(default_factory=dict)
    model_version: str = "cumulative-multilayer-ensemble-v1"
    timestamp: str


class AuditRequest(BaseModel):
    document: str
    document_id: Optional[str] = None


class TextExtractionResponse(BaseModel):
    filename: str
    content_type: Optional[str] = None
    characters: int
    text: str


class CredentialsRequest(BaseModel):
    username: str
    password: str


class UserProfile(BaseModel):
    id: int
    username: str
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: UserProfile


class AuditResponse(BaseModel):
    document: str
    total: int
    verified: int
    plausible: int
    hallucinations: int
    claims: List[Claim]


class ChatMessage(BaseModel):
    id: int
    session_id: str
    role: str = Field(pattern="^(user|assistant)$")
    message: str
    timestamp: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8_000)
    session_id: Optional[str] = Field(default=None, min_length=1, max_length=128)


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    messages: List[ChatMessage]


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: List[ChatMessage]


class HistorySummary(BaseModel):
    id: int
    title: str
    preview: str
    created_at: str
    total: int
    verified: int
    plausible: int
    hallucinations: int
    source_name: Optional[str] = None


class HistoryDetail(BaseModel):
    id: int
    title: str
    preview: str
    created_at: str
    source_name: Optional[str] = None
    audit: AuditResponse
