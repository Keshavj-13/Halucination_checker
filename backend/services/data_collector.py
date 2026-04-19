import json
import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from models.schemas import ClaimLogRecord, Evidence
from services.config import RUNTIME_LOG_PATH

logger = logging.getLogger("audit-api.data-collector")


class DataCollector:
    """Structured JSONL logging for model retraining and diagnostics."""

    def __init__(self, filepath: str | None = None):
        self.filepath = filepath or str(RUNTIME_LOG_PATH)
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)

    def collect(self, record: ClaimLogRecord):
        try:
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.model_dump(), ensure_ascii=False) + "\n")
            logger.info(f"Collected data for claim: {record.claim_text[:40]}...")
        except Exception as e:
            logger.error(f"Failed to collect data: {str(e)}")

    def collect_raw(
        self,
        document_id: str,
        claim_text: str,
        start_idx: int,
        end_idx: int,
        urls: list[str],
        evidence: list[Evidence],
        voter_results: Dict[str, Any],
        final_score: float,
        final_label: str,
        confidence: float,
        runtime_metadata: Dict[str, Any],
        model_version: str = "cumulative-multilayer-ensemble-v1",
    ) -> None:
        record = ClaimLogRecord(
            document_id=document_id,
            claim_text=claim_text,
            start_idx=start_idx,
            end_idx=end_idx,
            retrieved_urls=urls,
            evidence_chunks=evidence,
            source_reliability_scores=[ev.reliability_score for ev in evidence],
            voter_scores={k: float(v.get("confidence", 0.0)) for k, v in voter_results.items()},
            voter_results=voter_results,
            final_consensus_score=final_score,
            final_label=final_label,
            confidence=confidence,
            runtime_metadata=runtime_metadata,
            model_version=model_version,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.collect(record)


data_collector = DataCollector()
