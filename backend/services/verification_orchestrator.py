import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any
from models.schemas import Claim, Evidence, RuntimeMetadata, VoterResult
from services.voters.heuristic_voter import heuristic_voter
from services.voters.semantic_voter import semantic_voter
from services.voters.entity_voter import entity_voter
from services.voters.consistency_voter import consistency_voter
from services.voters.deterministic_voter import deterministic_voter
from services.data_collector import data_collector
from services.consensus_engine import consensus_engine
from services.config import VOTER_CPU_WORKERS, VOTER_TIMEOUT_SECONDS, VOTERS_SERIAL_MODE
from services.telemetry import telemetry

logger = logging.getLogger("audit-api.orchestrator")


class VerificationOrchestrator:
    """
    Orchestrates the ensemble and calibrated consensus computation.
    """

    def __init__(self):
        self._cpu_voter_pool = ThreadPoolExecutor(max_workers=VOTER_CPU_WORKERS)

    async def _run_cpu_voter(self, voter, text: str, evidence: List[Evidence]):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._cpu_voter_pool,
            lambda: asyncio.run(voter.vote(text, evidence)),
        )

    async def _timed(self, name: str, coro, timeout_s: float):
        started = asyncio.get_event_loop().time()
        try:
            result = await asyncio.wait_for(coro, timeout=max(timeout_s, 0.5))
        except Exception as exc:
            result = exc
        elapsed_ms = (asyncio.get_event_loop().time() - started) * 1000.0
        return name, result, elapsed_ms

    async def verify_multilayer(
        self,
        text: str,
        evidence: List[Evidence],
        document_id: str = "unknown-document",
        claim_key: str = "",
        start_idx: int = 0,
        end_idx: int = 0,
        urls: List[str] | None = None,
        retrieval_runtime_ms: float = 0.0,
        retrieval_cache_hits: int = 0,
        retrieval_failures: List[str] | None = None,
        retrieval_num_clusters: int | None = None,
        retrieval_independent_clusters: int | None = None,
        retrieval_cluster_support: float | None = None,
    ) -> Claim:
        logger.info(f"Running ensemble for: {text[:50]}...")
        telemetry.event("voting_start", document_id=document_id, claim_key=claim_key, stage="voting", message="ensemble voting started", payload={"num_evidence": len(evidence)})

        voting_started = asyncio.get_event_loop().time()
        timeout_s = max(VOTER_TIMEOUT_SECONDS, 0.5)
        if VOTERS_SERIAL_MODE:
            raw_results = [
                await self._timed("heuristic", self._run_cpu_voter(heuristic_voter, text, evidence), timeout_s),
                await self._timed("semantic", semantic_voter.vote(text, evidence), timeout_s),
                await self._timed("entity", self._run_cpu_voter(entity_voter, text, evidence), timeout_s),
                await self._timed("consistency", self._run_cpu_voter(consistency_voter, text, evidence), timeout_s),
                await self._timed("deterministic", self._run_cpu_voter(deterministic_voter, text, evidence), timeout_s),
            ]
        else:
            voter_tasks = [
                asyncio.create_task(self._timed("heuristic", self._run_cpu_voter(heuristic_voter, text, evidence), timeout_s)),
                asyncio.create_task(self._timed("semantic", semantic_voter.vote(text, evidence), timeout_s)),
                asyncio.create_task(self._timed("entity", self._run_cpu_voter(entity_voter, text, evidence), timeout_s)),
                asyncio.create_task(self._timed("consistency", self._run_cpu_voter(consistency_voter, text, evidence), timeout_s)),
                asyncio.create_task(self._timed("deterministic", self._run_cpu_voter(deterministic_voter, text, evidence), timeout_s)),
            ]

            raw_results = await asyncio.gather(*voter_tasks, return_exceptions=True)
        results = {}
        voter_runtime_ms = {}
        for result in raw_results:
            if isinstance(result, Exception):
                logger.error(f"Timed voter wrapper failed: {str(result)}")
                telemetry.event("voter_wrapper_error", document_id=document_id, claim_key=claim_key, stage="voting", message=str(result))
                continue

            name, voter_result, elapsed_ms = result
            voter_runtime_ms[name] = round(float(elapsed_ms), 2)
            if isinstance(voter_result, Exception):
                logger.error(f"Voter {name} failed: {str(voter_result)}")
                telemetry.event("voter_error", document_id=document_id, claim_key=claim_key, stage=f"voting.{name}", message=str(voter_result), payload={"runtime_ms": round(float(elapsed_ms), 2)})
                results[name] = {
                    "status": "Plausible",
                    "confidence": 0.0,
                    "reasoning": "Voter failed during verification.",
                }
            else:
                results[name] = voter_result
                telemetry.event(
                    "voter_done",
                    document_id=document_id,
                    claim_key=claim_key,
                    stage=f"voting.{name}",
                    message="voter completed",
                    payload={
                        "runtime_ms": round(float(elapsed_ms), 2),
                        "status": voter_result.get("status", "Plausible"),
                        "confidence": float(voter_result.get("confidence", 0.0)),
                    },
                )

        avg_reliability = sum(ev.reliability_score for ev in evidence) / len(evidence) if evidence else 0.0
        if retrieval_cluster_support is None:
            cluster_support = self._cluster_support_score(evidence)
        else:
            cluster_support = retrieval_cluster_support

        final_score, final_confidence, final_status, normalized_voter_scores = consensus_engine.combine(
            voter_results=results,
            source_reliability=avg_reliability,
            cluster_support=cluster_support,
        )

        stance_support = sum(1 for ev in evidence if (ev.stance or "").lower() == "support")
        stance_refute = sum(1 for ev in evidence if (ev.stance or "").lower() == "refute")
        stance_mention = sum(1 for ev in evidence if (ev.stance or "").lower() in {"mention", "quotation", "reported_belief"})
        n_ev = max(1, len(evidence))
        support_ratio = stance_support / n_ev
        refute_ratio = stance_refute / n_ev
        mention_ratio = stance_mention / n_ev

        # Mention is not endorsement: apply conservative downgrade when evidence is mostly mention/reporting.
        if mention_ratio >= 0.60 and support_ratio < 0.15:
            final_score = max(0.0, final_score - 0.16)

        # Strong refuting stance distribution should pull score down even with lexical overlap.
        if refute_ratio > support_ratio and refute_ratio >= 0.20:
            final_score = max(0.0, final_score - 0.10)

        det = results.get("deterministic", {})
        det_status = str(det.get("status", "Plausible"))
        det_meta = det.get("metadata", {}) if isinstance(det.get("metadata", {}), dict) else {}
        det_label = str(det_meta.get("deterministic_label", ""))

        # Honor strict deterministic overrides.
        if bool(det_meta.get("strong_refute_override", False)):
            final_status = "Hallucination"
            final_score = min(final_score, 0.22)
        elif det_label in {"Uncertain", "Conflicting"} and final_status == "Verified":
            final_status = "Plausible"
            final_score = min(final_score, 0.62)
        elif det_status == "Verified" and mention_ratio >= 0.65:
            final_status = "Plausible"
            final_score = min(final_score, 0.60)

        final_confidence = min(1.0, max(0.0, max(final_confidence, abs(final_score - 0.5) * 2.0)))

        best_evidence = sorted(evidence, key=lambda ev: ev.reliability_score, reverse=True)[:3]
        contradicting_evidence = [ev for ev in evidence if ev.support == "contradicting"][:3]

        voting_runtime_ms = (asyncio.get_event_loop().time() - voting_started) * 1000.0
        runtime_metadata = {
            "retrieval_runtime_ms": retrieval_runtime_ms,
            "voting_runtime_ms": voting_runtime_ms,
            "voter_runtime_ms": voter_runtime_ms,
            "num_urls": len(urls or []),
            "num_chunks": len(evidence),
            "num_clusters": retrieval_num_clusters if retrieval_num_clusters is not None else self._count_clusters(evidence),
            "independent_clusters": (
                retrieval_independent_clusters
                if retrieval_independent_clusters is not None
                else self._count_independent_clusters(evidence)
            ),
            "cluster_support": cluster_support,
            "cache_hits": retrieval_cache_hits,
            "external_failures": retrieval_failures or [],
        }

        data_collector.collect_raw(
            document_id=document_id,
            claim_text=text,
            start_idx=start_idx,
            end_idx=end_idx,
            urls=urls or [],
            evidence=evidence,
            voter_results=results,
            final_score=final_score,
            final_label=final_status,
            confidence=final_confidence,
            runtime_metadata=runtime_metadata,
        )
        telemetry.event(
            "voting_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="voting",
            message="ensemble voting completed",
            payload={
                "final_status": final_status,
                "final_score": round(float(final_score), 4),
                "confidence": round(float(final_confidence), 4),
                "voting_runtime_ms": round(float(voting_runtime_ms), 2),
                "stance_support_ratio": round(float(support_ratio), 3),
                "stance_refute_ratio": round(float(refute_ratio), 3),
                "stance_mention_ratio": round(float(mention_ratio), 3),
                "voter_runtime_ms": voter_runtime_ms,
            },
        )

        return Claim(
            text=text,
            status=final_status,
            label=final_status,
            final_score=round(final_score, 4),
            confidence=round(final_confidence, 4),
            evidence=evidence,
            voter_scores={name: round(float(score), 4) for name, score in normalized_voter_scores.items()},
            voter_results={
                name: VoterResult(
                    status=res.get("status", "Plausible"),
                    confidence=float(res.get("confidence", 0.0)),
                    reasoning=res.get("reasoning", ""),
                    score=res.get("score"),
                    metadata=res.get("metadata", {}),
                )
                for name, res in results.items()
            },
            best_evidence=best_evidence,
            contradicting_evidence=contradicting_evidence,
            source_reliability_explanation=(
                f"avg_source_reliability={avg_reliability:.2f}, cluster_support={cluster_support:.2f}, "
                f"num_clusters={runtime_metadata['num_clusters']}, "
                f"independent_clusters={runtime_metadata['independent_clusters']}"
            ),
            runtime=RuntimeMetadata(
                total_runtime_ms=round(retrieval_runtime_ms + voting_runtime_ms, 2),
                retrieval_runtime_ms=round(retrieval_runtime_ms, 2),
                voting_runtime_ms=round(voting_runtime_ms, 2),
                num_urls=len(urls or []),
                num_chunks=len(evidence),
                cache_hits=retrieval_cache_hits,
                external_failures=retrieval_failures or [],
            ),
        )

    def _cluster_support_score(self, evidence: List[Evidence]) -> float:
        if not evidence:
            return 0.0
        num_clusters = self._count_clusters(evidence)
        independent = self._count_independent_clusters(evidence)
        if num_clusters <= 1:
            return 0.35
        return min(0.35 + 0.2 * (num_clusters - 1) + 0.1 * max(0, independent - 1), 1.0)

    def _count_clusters(self, evidence: List[Evidence]) -> int:
        cluster_ids = {ev.cluster_id for ev in evidence if ev.cluster_id is not None}
        return len(cluster_ids) if cluster_ids else 0

    def _count_independent_clusters(self, evidence: List[Evidence]) -> int:
        by_cluster: Dict[int, set[str]] = {}
        for ev in evidence:
            if ev.cluster_id is None:
                continue
            by_cluster.setdefault(ev.cluster_id, set()).add(ev.source_domain or "")
        return sum(1 for domains in by_cluster.values() if len([d for d in domains if d]) >= 1)

orchestrator = VerificationOrchestrator()
