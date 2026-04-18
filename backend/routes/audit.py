from fastapi import APIRouter, HTTPException
from models.schemas import AuditRequest, AuditResponse
from services.claim_extractor import extract_claims
from services.verifier import verify_claims, verify_claims_stream
from data.sample_data import SAMPLE_RESPONSE
import logging
from fastapi.responses import StreamingResponse
import json

router = APIRouter(prefix="/audit", tags=["audit"])
logger = logging.getLogger("audit-api.routes")

@router.post("/", response_model=AuditResponse)
async def run_audit(body: AuditRequest):
    logger.info(f"Received audit request for document length: {len(body.document)}")
    
    # 1. Extract Claims (with indices)
    claims_data = await extract_claims(body.document)
    
    # 2. Verify Claims (Multilayer)
    verified_claims = await verify_claims(claims_data)
    
    # 3. Calculate Stats
    verified = len([c for c in verified_claims if c.status == "Verified"])
    plausible = len([c for c in verified_claims if c.status == "Plausible"])
    hallucinations = len([c for c in verified_claims if c.status == "Hallucination"])
    
    return AuditResponse(
        document=body.document,
        total=len(verified_claims),
        verified=verified,
        plausible=plausible,
        hallucinations=hallucinations,
        claims=verified_claims
    )

@router.post("/stream")
async def run_audit_stream(body: AuditRequest):
    logger.info(f"Received streaming audit request")
    claims_data = await extract_claims(body.document)
    
    async def event_generator():
        yield f"data: {json.dumps({'type': 'start', 'total': len(claims_data)})}\n\n"
        
        async for claim in verify_claims_stream(claims_data):
            yield f"data: {json.dumps({'type': 'claim', 'claim': claim.model_dump()})}\n\n"
            
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/sample", response_model=AuditResponse)
def get_sample():
    return SAMPLE_RESPONSE
