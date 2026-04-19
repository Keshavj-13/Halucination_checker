from fastapi import APIRouter, HTTPException
from models.schemas import AuditRequest, AuditResponse
from services.claim_extractor import extract_claims
from services.verifier import verify_claims, verify_claim
from services.retrieval_pipeline import retrieval_pipeline
from services.verification_orchestrator import orchestrator
from services.config import (
    CPU_WORKERS,
    VOTER_CPU_WORKERS,
    MAX_CLAIMS_IN_FLIGHT,
    SCRAPE_CONCURRENCY,
    RETRIEVAL_DEADLINE_SECONDS,
    CLAIM_PIPELINE_DEADLINE_SECONDS,
    LLM_VOTER_ENABLED,
    LLM_TIMEOUT_SECONDS,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MAX_IN_FLIGHT,
    OLLAMA_NUM_GPU,
    PIPELINE_SERIAL_MODE,
)
from data.sample_data import SAMPLE_RESPONSE
import logging
from fastapi.responses import StreamingResponse
import json
import uuid
import time
import asyncio
from services.telemetry import telemetry

router = APIRouter(prefix="/audit", tags=["audit"])
logger = logging.getLogger("audit-api.routes")

@router.post("/", response_model=AuditResponse)
async def run_audit(body: AuditRequest):
    logger.info(f"Received audit request for document length: {len(body.document)}")
    document_id = body.document_id or str(uuid.uuid4())
    started = time.perf_counter()
    telemetry.event("audit_request_start", document_id=document_id, stage="audit", message="non-stream request started", payload={"document_len": len(body.document)})
    
    # 1. Extract Claims (with indices)
    claims_data = await extract_claims(body.document)
    telemetry.event("claims_extracted", document_id=document_id, stage="extract", message=f"extracted {len(claims_data)} claims", payload={"num_claims": len(claims_data)})
    for claim in claims_data:
        claim["document_id"] = document_id
    
    # 2. Verify Claims (Multilayer)
    verified_claims = await verify_claims(claims_data)
    telemetry.event("claims_verified", document_id=document_id, stage="verify", message=f"verified {len(verified_claims)} claims", payload={"num_claims": len(verified_claims)})
    
    # 3. Calculate Stats
    verified = len([c for c in verified_claims if c.status == "Verified"])
    plausible = len([c for c in verified_claims if c.status == "Plausible"])
    hallucinations = len([c for c in verified_claims if c.status == "Hallucination"])
    telemetry.event(
        "audit_request_done",
        document_id=document_id,
        stage="audit",
        message="non-stream request completed",
        payload={
            "total": len(verified_claims),
            "verified": verified,
            "plausible": plausible,
            "hallucinations": hallucinations,
            "runtime_ms": round((time.perf_counter() - started) * 1000.0, 2),
        },
    )
    
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
    document_id = body.document_id or str(uuid.uuid4())
    telemetry.event("audit_stream_start", document_id=document_id, stage="stream", message="streaming request started", payload={"document_len": len(body.document)})
    
    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'resources', 'resources': {'cpu_workers': CPU_WORKERS, 'voter_cpu_workers': VOTER_CPU_WORKERS, 'max_claims_in_flight': MAX_CLAIMS_IN_FLIGHT, 'scrape_concurrency': SCRAPE_CONCURRENCY, 'retrieval_deadline_seconds': RETRIEVAL_DEADLINE_SECONDS, 'claim_pipeline_deadline_seconds': CLAIM_PIPELINE_DEADLINE_SECONDS, 'llm_voter_enabled': LLM_VOTER_ENABLED, 'llm_timeout_seconds': LLM_TIMEOUT_SECONDS, 'embedding_batch_size': EMBEDDING_BATCH_SIZE, 'embedding_max_in_flight': EMBEDDING_MAX_IN_FLIGHT, 'ollama_num_gpu': OLLAMA_NUM_GPU}})}\n\n"
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'extracting_claims', 'message': 'Extracting atomic claims...'})}\n\n"

            claims_data = await extract_claims(body.document)
            telemetry.event("claims_extracted", document_id=document_id, stage="extract", message=f"extracted {len(claims_data)} claims", payload={"num_claims": len(claims_data)})
            for claim in claims_data:
                claim["document_id"] = document_id

            pending_claims = [
                {
                    "text": c["text"],
                    "start_idx": c["start"],
                    "end_idx": c["end"],
                    "status": "Pending",
                    "confidence": 0.0,
                    "evidence": [],
                    "runtime": {"total_runtime_ms": 0.0},
                }
                for c in claims_data
            ]

            total = len(claims_data)
            telemetry.start_document_progress(document_id, total)
            yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"
            yield f"data: {json.dumps({'type': 'claims_extracted', 'claims': pending_claims})}\n\n"
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'verifying_claims', 'message': f'Verifying {total} claims in parallel...'})}\n\n"

            completed = 0
            verified = 0
            plausible = 0
            hallucinations = 0

            async def _run_claim(c: dict):
                telemetry.event(
                    "claim_task_started",
                    document_id=document_id,
                    claim_key=f"{c['start']}:{c['end']}",
                    stage="verify",
                    message="claim task started",
                )
                return await verify_claim(
                    text=c["text"],
                    document_id=c.get("document_id", document_id),
                    start_idx=c["start"],
                    end_idx=c["end"],
                )

            if PIPELINE_SERIAL_MODE:
                for c in claims_data:
                    claim = await _run_claim(c)
                    completed += 1
                    if claim.status == "Verified":
                        verified += 1
                    elif claim.status == "Hallucination":
                        hallucinations += 1
                    else:
                        plausible += 1

                    yield f"data: {json.dumps({'type': 'claim', 'claim': claim.model_dump(), 'completed': completed, 'total': total})}\n\n"
                    scrape = telemetry.get_document_scrape_snapshot(document_id)
                    yield f"data: {json.dumps({'type': 'progress', 'completed': completed, 'total': total, 'verified': verified, 'plausible': plausible, 'hallucinations': hallucinations, 'in_flight': 0, 'scrape': scrape})}\n\n"
                    telemetry.update_document_progress(document_id, completed, total, claim.status)
                    telemetry.event(
                        "claim_streamed",
                        document_id=document_id,
                        claim_key=f"{claim.start_idx}:{claim.end_idx}",
                        stage="verify",
                        message=f"claim completed {completed}/{total}",
                        payload={
                            "status": claim.status,
                            "confidence": claim.confidence,
                            "runtime": claim.runtime.model_dump() if claim.runtime else {},
                            "in_flight": 0,
                        },
                    )
            else:
                sem = asyncio.Semaphore(MAX_CLAIMS_IN_FLIGHT)
                async def _run_claim_with_sem(c: dict):
                    async with sem:
                        return await _run_claim(c)

                pending_tasks = {asyncio.create_task(_run_claim_with_sem(c)) for c in claims_data}
                last_heartbeat = time.perf_counter()

                while pending_tasks:
                    done, pending_tasks = await asyncio.wait(
                        pending_tasks,
                        timeout=0.4,
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if not done:
                        now = time.perf_counter()
                        if now - last_heartbeat >= 0.4:
                            in_flight = len(pending_tasks)
                            scrape = telemetry.get_document_scrape_snapshot(document_id)
                            yield f"data: {json.dumps({'type': 'heartbeat', 'completed': completed, 'total': total, 'in_flight': in_flight, 'scrape': scrape})}\n\n"
                            telemetry.event(
                                "stream_heartbeat",
                                document_id=document_id,
                                stage="verify",
                                message=f"heartbeat completed={completed} in_flight={in_flight}",
                                payload={"completed": completed, "total": total, "in_flight": in_flight, "scrape": scrape},
                            )
                            last_heartbeat = now
                        continue

                    for task in done:
                        claim = await task
                        completed += 1
                        if claim.status == "Verified":
                            verified += 1
                        elif claim.status == "Hallucination":
                            hallucinations += 1
                        else:
                            plausible += 1

                        yield f"data: {json.dumps({'type': 'claim', 'claim': claim.model_dump(), 'completed': completed, 'total': total})}\n\n"
                        scrape = telemetry.get_document_scrape_snapshot(document_id)
                        yield f"data: {json.dumps({'type': 'progress', 'completed': completed, 'total': total, 'verified': verified, 'plausible': plausible, 'hallucinations': hallucinations, 'in_flight': len(pending_tasks), 'scrape': scrape})}\n\n"
                        telemetry.update_document_progress(document_id, completed, total, claim.status)
                        telemetry.event(
                            "claim_streamed",
                            document_id=document_id,
                            claim_key=f"{claim.start_idx}:{claim.end_idx}",
                            stage="verify",
                            message=f"claim completed {completed}/{total}",
                            payload={
                                "status": claim.status,
                                "confidence": claim.confidence,
                                "runtime": claim.runtime.model_dump() if claim.runtime else {},
                                "in_flight": len(pending_tasks),
                            },
                        )

            yield f"data: {json.dumps({'type': 'done', 'verified': verified, 'plausible': plausible, 'hallucinations': hallucinations, 'total': total})}\n\n"
            telemetry.finish_document_progress(document_id)
            telemetry.event(
                "audit_stream_done",
                document_id=document_id,
                stage="stream",
                message="streaming request completed",
                payload={"total": total, "verified": verified, "plausible": plausible, "hallucinations": hallucinations},
            )
        except Exception as e:
            logger.exception("Streaming audit failed")
            telemetry.finish_document_progress(document_id)
            telemetry.event("audit_stream_error", document_id=document_id, stage="stream", message=str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/sample", response_model=AuditResponse)
def get_sample():
    return SAMPLE_RESPONSE


@router.post("/probe")
async def run_probe(body: AuditRequest, max_claims: int = 4):
    """Fast diagnostic endpoint: isolated extraction/retrieval/voting probes on a small claim subset."""
    document_id = body.document_id or str(uuid.uuid4())
    max_claims = max(1, min(max_claims, 8))
    started = time.perf_counter()

    claims_data = await extract_claims(body.document)
    subset = claims_data[:max_claims]

    rows = []
    for idx, c in enumerate(subset, 1):
        claim_key = f"{c['start']}:{c['end']}"
        row = {
            "index": idx,
            "claim_key": claim_key,
            "text": c["text"],
            "retrieval": {},
            "voting": {},
        }

        retrieval_started = time.perf_counter()
        try:
            retrieval = await asyncio.wait_for(
                retrieval_pipeline.retrieve(c["text"], document_id=document_id, claim_key=claim_key),
                timeout=12.0,
            )
            row["retrieval"] = {
                "ok": True,
                "ms": round((time.perf_counter() - retrieval_started) * 1000.0, 2),
                "num_urls": len(retrieval.urls),
                "num_evidence": len(retrieval.evidence),
                "cache_hits": retrieval.cache_hits,
                "failures": retrieval.failures,
            }
        except Exception as exc:
            row["retrieval"] = {
                "ok": False,
                "ms": round((time.perf_counter() - retrieval_started) * 1000.0, 2),
                "error": str(exc),
            }
            rows.append(row)
            continue

        voting_started = time.perf_counter()
        try:
            out = await asyncio.wait_for(
                orchestrator.verify_multilayer(
                    text=c["text"],
                    evidence=retrieval.evidence,
                    document_id=document_id,
                    claim_key=claim_key,
                    start_idx=c["start"],
                    end_idx=c["end"],
                    urls=retrieval.urls,
                    retrieval_runtime_ms=retrieval.runtime_ms,
                    retrieval_cache_hits=retrieval.cache_hits,
                    retrieval_failures=retrieval.failures,
                    retrieval_num_clusters=retrieval.num_clusters,
                    retrieval_independent_clusters=retrieval.independent_clusters,
                    retrieval_cluster_support=retrieval.cluster_support,
                ),
                timeout=10.0,
            )
            row["voting"] = {
                "ok": True,
                "ms": round((time.perf_counter() - voting_started) * 1000.0, 2),
                "status": out.status,
                "confidence": out.confidence,
                "num_voters": len(out.voter_scores or {}),
                "num_evidence": len(out.evidence or []),
            }
        except Exception as exc:
            row["voting"] = {
                "ok": False,
                "ms": round((time.perf_counter() - voting_started) * 1000.0, 2),
                "error": str(exc),
            }

        rows.append(row)

    retrieval_ok = sum(1 for r in rows if r.get("retrieval", {}).get("ok"))
    voting_ok = sum(1 for r in rows if r.get("voting", {}).get("ok"))

    return {
        "document_id": document_id,
        "claims_extracted": len(claims_data),
        "claims_probed": len(rows),
        "retrieval_ok": retrieval_ok,
        "voting_ok": voting_ok,
        "runtime_ms": round((time.perf_counter() - started) * 1000.0, 2),
        "rows": rows,
    }
