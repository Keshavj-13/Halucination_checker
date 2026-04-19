import logging
import asyncio
import time
from concurrent.futures import ProcessPoolExecutor
from typing import List
from models.schemas import Claim
from services.verification_orchestrator import orchestrator
from services.retrieval_pipeline import retrieval_pipeline
from services.data_collector import data_collector
from services.config import CLAIM_PIPELINE_DEADLINE_SECONDS, MAX_CLAIMS_IN_FLIGHT, VOTING_TIMEOUT_SECONDS, RETRIEVAL_STAGE_TIMEOUT_SECONDS, PIPELINE_SERIAL_MODE, PIPELINE_PROCESS_MODE, CLAIM_PROCESS_WORKERS
from services.telemetry import telemetry

logger = logging.getLogger("audit-api.verifier")

_process_pool = ProcessPoolExecutor(max_workers=CLAIM_PROCESS_WORKERS) if PIPELINE_PROCESS_MODE else None


def _verify_claim_process_entry(payload: dict) -> dict:
    import asyncio
    from services.verifier import verify_claim

    claim = asyncio.run(
        verify_claim(
            text=payload["text"],
            document_id=payload.get("document_id", "unknown-document"),
            start_idx=int(payload.get("start_idx", 0)),
            end_idx=int(payload.get("end_idx", 0)),
            _process_dispatched=True,
        )
    )
    return claim.model_dump()


def shutdown_verifier_executors() -> None:
    global _process_pool
    if _process_pool is not None:
        _process_pool.shutdown(wait=False, cancel_futures=True)
        _process_pool = None


async def verify_claim(text: str, document_id: str = "unknown-document", start_idx: int = 0, end_idx: int = 0, _process_dispatched: bool = False) -> Claim:
    """Full multilayer verification flow: Search -> Scrape/Chunk -> Vote -> Calibrated consensus."""
    if PIPELINE_PROCESS_MODE and not _process_dispatched and _process_pool is not None:
        loop = asyncio.get_running_loop()
        dump = await loop.run_in_executor(
            _process_pool,
            _verify_claim_process_entry,
            {
                "text": text,
                "document_id": document_id,
                "start_idx": start_idx,
                "end_idx": end_idx,
            },
        )
        return Claim.model_validate(dump)

    logger.info(f"Starting multilayer verification for: {text[:50]}...")

    started = time.perf_counter()
    claim_key = f"{start_idx}:{end_idx}"
    active_stage = "retrieval"
    telemetry.event("claim_start", document_id=document_id, claim_key=claim_key, stage="pipeline", message=text[:120])
    base_retrieval_timeout = max(RETRIEVAL_STAGE_TIMEOUT_SECONDS, 4.0)
    base_voting_timeout = max(VOTING_TIMEOUT_SECONDS, 4.0)

    async def _run_once(retrieval_timeout_s: float, voting_timeout_s: float, attempt: int) -> Claim:
        nonlocal active_stage
        retrieval_started = time.perf_counter()
        retrieval = await asyncio.wait_for(
            retrieval_pipeline.retrieve(text, document_id=document_id, claim_key=claim_key),
            timeout=retrieval_timeout_s,
        )
        telemetry.event(
            "claim_retrieval_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="retrieval",
            message=f"retrieval completed (attempt {attempt})",
            payload={
                "runtime_ms": round((time.perf_counter() - retrieval_started) * 1000.0, 2),
                "num_urls": len(retrieval.urls),
                "num_chunks": len(retrieval.evidence),
                "cache_hits": retrieval.cache_hits,
                "failures": retrieval.failures,
                "attempt": attempt,
            },
        )

        effective_voting_timeout = voting_timeout_s
        if retrieval.evidence:
            effective_voting_timeout = max(effective_voting_timeout, 8.0)

        active_stage = "voting"
        voting_started = time.perf_counter()
        claim = await asyncio.wait_for(
            orchestrator.verify_multilayer(
                text=text,
                evidence=retrieval.evidence,
                document_id=document_id,
                claim_key=claim_key,
                start_idx=start_idx,
                end_idx=end_idx,
                urls=retrieval.urls,
                retrieval_runtime_ms=retrieval.runtime_ms,
                retrieval_cache_hits=retrieval.cache_hits,
                retrieval_failures=retrieval.failures,
                retrieval_num_clusters=retrieval.num_clusters,
                retrieval_independent_clusters=retrieval.independent_clusters,
                retrieval_cluster_support=retrieval.cluster_support,
            ),
            timeout=effective_voting_timeout,
        )
        telemetry.event(
            "claim_voting_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="voting",
            message=f"voting completed (attempt {attempt})",
            payload={
                "runtime_ms": round((time.perf_counter() - voting_started) * 1000.0, 2),
                "status": claim.status,
                "confidence": claim.confidence,
                "attempt": attempt,
            },
        )
        claim.start_idx = start_idx
        claim.end_idx = end_idx
        telemetry.event(
            "claim_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="pipeline",
            message="claim pipeline done",
            payload={"runtime_ms": round((time.perf_counter() - started) * 1000.0, 2), "status": claim.status, "attempt": attempt},
        )
        return claim

    try:
        return await _run_once(base_retrieval_timeout, base_voting_timeout, attempt=1)

    except asyncio.TimeoutError:
        first_elapsed_ms = (time.perf_counter() - started) * 1000.0
        first_msg = (
            f"retrieval timeout exceeded {base_retrieval_timeout:.2f}s"
            if active_stage == "retrieval"
            else f"voting timeout exceeded {base_voting_timeout:.2f}s"
        )
        telemetry.event(
            "claim_timeout_retry",
            document_id=document_id,
            claim_key=claim_key,
            stage="pipeline",
            message=f"{first_msg}; retrying once with expanded timeout",
            payload={"runtime_ms": round(first_elapsed_ms, 2)},
        )

        retry_retrieval_timeout = min(max(base_retrieval_timeout * 1.6, base_retrieval_timeout + 2.0), 24.0)
        retry_voting_timeout = min(max(base_voting_timeout * 1.6, base_voting_timeout + 2.0), 24.0)
        active_stage = "retrieval"
        try:
            return await _run_once(retry_retrieval_timeout, retry_voting_timeout, attempt=2)
        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if active_stage == "retrieval":
                msg = f"retrieval timeout exceeded {retry_retrieval_timeout:.2f}s after retry"
            else:
                msg = f"voting timeout exceeded {retry_voting_timeout:.2f}s after retry"
            logger.error(f"Verification timeout for claim: {text[:40]}... ({msg})")
            data_collector.collect_raw(
                document_id=document_id,
                claim_text=text,
                start_idx=start_idx,
                end_idx=end_idx,
                urls=[],
                evidence=[],
                voter_results={},
                final_score=0.0,
                final_label="Plausible",
                confidence=0.0,
                runtime_metadata={
                    "total_runtime_ms": round(elapsed_ms, 2),
                    "external_failures": [msg],
                },
            )
            telemetry.event("claim_timeout", document_id=document_id, claim_key=claim_key, stage="pipeline", message=msg, payload={"runtime_ms": round(elapsed_ms, 2)})
            return Claim(text=text, status="Plausible", confidence=0.0, evidence=[], start_idx=start_idx, end_idx=end_idx)

    except Exception as e:
        logger.error(f"Verification flow failed: {str(e)}")
        telemetry.event("claim_error", document_id=document_id, claim_key=claim_key, stage="pipeline", message=str(e))
        return Claim(text=text, status="Plausible", confidence=0.0, evidence=[], start_idx=start_idx, end_idx=end_idx)


async def verify_claims(claims_data: List[dict]) -> List[Claim]:
    """Verify all claims in parallel."""
    if PIPELINE_SERIAL_MODE:
        out: List[Claim] = []
        for c in claims_data:
            out.append(
                await verify_claim(
                    text=c["text"],
                    document_id=c.get("document_id", "unknown-document"),
                    start_idx=c["start"],
                    end_idx=c["end"],
                )
            )
        return out

    sem = asyncio.Semaphore(MAX_CLAIMS_IN_FLIGHT)

    async def _run(c: dict) -> Claim:
        async with sem:
            return await verify_claim(
                text=c["text"],
                document_id=c.get("document_id", "unknown-document"),
                start_idx=c["start"],
                end_idx=c["end"],
            )

    tasks = [_run(c) for c in claims_data]
    return list(await asyncio.gather(*tasks, return_exceptions=False))


async def verify_claims_stream(claims_data: List[dict]):
    """Stream results as they complete."""
    if PIPELINE_SERIAL_MODE:
        for claim_data in claims_data:
            result = await verify_claim(
                text=claim_data["text"],
                document_id=claim_data.get("document_id", "unknown-document"),
                start_idx=claim_data["start"],
                end_idx=claim_data["end"],
            )
            result.start_idx = claim_data["start"]
            result.end_idx = claim_data["end"]
            yield result
        return

    sem = asyncio.Semaphore(MAX_CLAIMS_IN_FLIGHT)

    async def _verify_with_indices(claim_data: dict):
        async with sem:
            result = await verify_claim(
                text=claim_data["text"],
                document_id=claim_data.get("document_id", "unknown-document"),
                start_idx=claim_data["start"],
                end_idx=claim_data["end"],
            )
        return result, claim_data["start"], claim_data["end"]

    tasks = [_verify_with_indices(c) for c in claims_data]
    for task in asyncio.as_completed(tasks):
        result, start, end = await task
        result.start_idx = start
        result.end_idx = end
        yield result
