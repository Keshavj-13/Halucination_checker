import logging
import asyncio
import time
from concurrent.futures import ProcessPoolExecutor
from typing import List
from models.schemas import Claim
from services.verification_orchestrator import orchestrator
from services.retrieval_pipeline import retrieval_pipeline
from services.trusted_verifier import verify_with_trusted_knowledge
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
            structured_claim=payload.get("structured_claim"),
            claim_type=payload.get("claim_type"),
            _process_dispatched=True,
        )
    )
    return claim.model_dump()


def shutdown_verifier_executors() -> None:
    global _process_pool
    if _process_pool is not None:
        _process_pool.shutdown(wait=False, cancel_futures=True)
        _process_pool = None


async def verify_claim(
    text: str,
    document_id: str = "unknown-document",
    start_idx: int = 0,
    end_idx: int = 0,
    structured_claim: dict | None = None,
    claim_type: str | None = None,
    _process_dispatched: bool = False,
) -> Claim:
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
                "structured_claim": structured_claim,
                "claim_type": claim_type,
            },
        )
        return Claim.model_validate(dump)

    logger.info(f"Starting multilayer verification for: {text[:50]}...")

    if (claim_type or "").upper() in {"SUBJECTIVE", "UNVERIFIABLE"}:
        return Claim(
            text=text,
            status="Plausible",
            label="UNVERIFIABLE",
            confidence=0.95,
            evidence=[],
            start_idx=start_idx,
            end_idx=end_idx,
            final_score=0.5,
            source_reliability_explanation="claim_type excluded from hard verification",
            proof_trace={
                "original_claim_text": text,
                "structured_claim": structured_claim or {},
                "claim_type": claim_type or "UNVERIFIABLE",
                "retrieved_evidence": [],
                "source_urls": [],
                "comparison_steps": ["claim excluded by type gate"],
                "scoring_rationale": "subjective or not structurally verifiable",
                "final_verdict": "UNVERIFIABLE",
                "confidence": 0.95,
                "negation_or_temporal_reasoning": {},
            },
        )

    started = time.perf_counter()
    claim_key = f"{start_idx}:{end_idx}"
    active_stage = "retrieval"
    telemetry.event("claim_start", document_id=document_id, claim_key=claim_key, stage="pipeline", message=text[:120])
    base_retrieval_timeout = max(RETRIEVAL_STAGE_TIMEOUT_SECONDS, 4.0)
    base_voting_timeout = max(VOTING_TIMEOUT_SECONDS, 4.0)

    async def _run_once(retrieval_timeout_s: float, voting_timeout_s: float, attempt: int) -> Claim:
        nonlocal active_stage
        trusted = verify_with_trusted_knowledge(text)
        telemetry.event(
            "claim_trusted_check_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="trusted",
            message=f"trusted check domain={trusted.domain}",
            payload={
                "domain": trusted.domain,
                "relation": trusted.relation,
                "entities": trusted.entities[:6],
                "numeric_values": trusted.numeric_values[:6],
                "units": trusted.units[:6],
                "status": trusted.status,
                "confidence": trusted.confidence,
                "reason": trusted.reason,
                "insufficient": trusted.insufficient,
            },
        )

        if trusted.status in {"Verified", "Hallucination"} and trusted.confidence >= 0.98 and trusted.evidence:
            trusted_label = "VERIFIED" if trusted.status == "Verified" else "REFUTED"
            short = Claim(
                text=text,
                status=trusted.status,
                label=trusted_label,
                final_score=1.0 if trusted.status == "Verified" else 0.0,
                confidence=trusted.confidence,
                evidence=trusted.evidence,
                start_idx=start_idx,
                end_idx=end_idx,
                source_reliability_explanation=f"trusted_layer domain={trusted.domain} reason={trusted.reason}",
            )
            telemetry.event(
                "claim_short_circuit_trusted",
                document_id=document_id,
                claim_key=claim_key,
                stage="trusted",
                message=f"short-circuit via trusted layer ({trusted.status})",
                payload={"confidence": trusted.confidence, "domain": trusted.domain, "reason": trusted.reason},
            )
            return short

        retrieval_started = time.perf_counter()
        retrieval = await asyncio.wait_for(
            retrieval_pipeline.retrieve(
                text,
                document_id=document_id,
                claim_key=claim_key,
                structured_claim=structured_claim,
                claim_type=claim_type,
            ),
            timeout=retrieval_timeout_s,
        )

        combined_evidence = list(trusted.evidence)
        seen = {(ev.url, ev.snippet) for ev in combined_evidence}
        for ev in retrieval.evidence:
            key = (ev.url, ev.snippet)
            if key in seen:
                continue
            seen.add(key)
            combined_evidence.append(ev)

        if trusted.evidence and combined_evidence:
            retrieval.evidence = combined_evidence
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
                "trusted_seeded_evidence": len(trusted.evidence),
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
                structured_claim=structured_claim,
                claim_type=claim_type,
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
                final_label="UNCERTAIN",
                confidence=0.0,
                runtime_metadata={
                    "total_runtime_ms": round(elapsed_ms, 2),
                    "external_failures": [msg],
                },
            )
            telemetry.event("claim_timeout", document_id=document_id, claim_key=claim_key, stage="pipeline", message=msg, payload={"runtime_ms": round(elapsed_ms, 2)})
            return Claim(text=text, status="Plausible", label="UNCERTAIN", confidence=0.0, evidence=[], start_idx=start_idx, end_idx=end_idx)

    except Exception as e:
        logger.error(f"Verification flow failed: {str(e)}")
        telemetry.event("claim_error", document_id=document_id, claim_key=claim_key, stage="pipeline", message=str(e))
        return Claim(text=text, status="Plausible", label="UNCERTAIN", confidence=0.0, evidence=[], start_idx=start_idx, end_idx=end_idx)


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
                    structured_claim=c.get("structured_claim"),
                    claim_type=c.get("claim_type"),
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
                structured_claim=c.get("structured_claim"),
                claim_type=c.get("claim_type"),
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
                structured_claim=claim_data.get("structured_claim"),
                claim_type=claim_data.get("claim_type"),
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
                structured_claim=claim_data.get("structured_claim"),
                claim_type=claim_data.get("claim_type"),
            )
        return result, claim_data["start"], claim_data["end"]

    tasks = [_verify_with_indices(c) for c in claims_data]
    for task in asyncio.as_completed(tasks):
        result, start, end = await task
        result.start_idx = start
        result.end_idx = end
        yield result


def audit_claim(text: str) -> dict:
    """Synchronous deterministic verifier entrypoint for architecture tests."""
    from services.claim_extractor import extract_triplets
    from services.retrieval_router import retrieve_evidence
    from services.nli_voter import nli_score

    triplets = extract_triplets(text)
    if not triplets:
        return {
            "verdict": "UNVERIFIABLE",
            "triplet_results": [],
            "proof_trace": {
                "steps": [],
                "summary": "no structured claims",
            },
        }

    triplet_results = []
    steps = []

    for t in triplets:
        evidence = retrieve_evidence(t)
        if not evidence:
            verdict = "UNCERTAIN"
            best = {"entailment": 0.0, "contradiction": 0.0, "neutral": 1.0}
        else:
            scores = []
            pred_surface = f"not {t.predicate}" if t.negated else t.predicate
            claim_surface = f"{t.subject} {pred_surface} {t.object}".strip()
            for ev in evidence:
                scores.append(nli_score(claim_surface, ev.snippet))
            best = max(scores, key=lambda s: (s["entailment"] - s["contradiction"], s["entailment"]))

            if best["entailment"] >= best["contradiction"] + 0.15:
                verdict = "VERIFIED"
            elif best["contradiction"] >= best["entailment"] + 0.15:
                verdict = "REFUTED"
            else:
                verdict = "PLAUSIBLE"

        triplet_results.append(
            {
                "triplet": {
                    "subject": t.subject,
                    "predicate": t.predicate,
                    "predicate_canonical": t.predicate_canonical,
                    "object": t.object,
                    "claim_type": t.claim_type.value,
                    "negated": t.negated,
                },
                "verdict": verdict,
                "nli": best,
                "evidence_count": len(evidence),
            }
        )
        steps.append(
            {
                "claim_structured": triplet_results[-1]["triplet"],
                "verdict": verdict,
                "nli": best,
            }
        )

    verdicts = [r["verdict"] for r in triplet_results]
    if all(v == "VERIFIED" for v in verdicts):
        overall = "VERIFIED"
    elif all(v in {"UNCERTAIN", "UNVERIFIABLE"} for v in verdicts):
        overall = "UNCERTAIN"
    elif "REFUTED" in verdicts and "VERIFIED" in verdicts:
        overall = "CONFLICTING"
    elif "REFUTED" in verdicts:
        overall = "REFUTED"
    elif "VERIFIED" in verdicts:
        overall = "PLAUSIBLE"
    else:
        overall = "PLAUSIBLE"

    return {
        "verdict": overall,
        "triplet_results": triplet_results,
        "proof_trace": {
            "steps": steps,
            "summary": overall,
        },
    }
