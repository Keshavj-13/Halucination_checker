from fastapi import APIRouter
from models.schemas import AuditRequest, AuditResponse
from services.claim_extractor import extract_claims
from services.verifier import verify_claims
from data.sample_data import SAMPLE_RESPONSE

import logging

logger = logging.getLogger("audit-api.routes")
router = APIRouter()


@router.post("/audit", response_model=AuditResponse)
def run_audit(body: AuditRequest):
    logger.info(f"Received audit request for document (length: {len(body.document)})")
    claims = extract_claims(body.document)
    logger.info(f"Extracted {len(claims)} claims")
    
    verified_claims = verify_claims(claims)
    
    verified = sum(1 for c in verified_claims if c.status == "Verified")
    plausible = sum(1 for c in verified_claims if c.status == "Plausible")
    hallucinations = sum(1 for c in verified_claims if c.status == "Hallucination")

    logger.info(f"Audit complete: {verified} verified, {plausible} plausible, {hallucinations} hallucinations")

    return AuditResponse(
        claims=verified_claims,
        total=len(verified_claims),
        verified=verified,
        plausible=plausible,
        hallucinations=hallucinations,
    )


@router.get("/sample", response_model=AuditResponse)
def get_sample():
    return SAMPLE_RESPONSE
