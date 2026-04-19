from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from services.config import TRACE_CONSOLE_EVENTS, TRACE_ENABLED, TRACE_LOG_PATH, TRACE_TQDM_ENABLED

logger = logging.getLogger("audit-api.telemetry")

try:
    from tqdm.auto import tqdm
except Exception:  # pragma: no cover
    tqdm = None


@dataclass
class _ProgressHandle:
    bar: Any
    total: int
    completed: int = 0


class RuntimeTelemetry:
    def __init__(self) -> None:
        self.enabled = TRACE_ENABLED
        self.console_events = TRACE_CONSOLE_EVENTS
        self.tqdm_enabled = TRACE_TQDM_ENABLED and tqdm is not None
        self.log_path = TRACE_LOG_PATH
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._bars: dict[str, _ProgressHandle] = {}
        self._doc_totals: dict[str, int] = {}
        self._stage_bars: dict[str, dict[str, _ProgressHandle]] = {}
        self._doc_scrape: dict[str, dict[str, int]] = {}

    def event(self, event_type: str, *, document_id: str | None = None, claim_key: str | None = None, stage: str = "", message: str = "", payload: dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return

        now_utc = datetime.now(timezone.utc).isoformat()
        perf_ms = time.perf_counter_ns() // 1_000_000
        rec = {
            "ts_utc": now_utc,
            "perf_ms": int(perf_ms),
            "event_type": event_type,
            "document_id": document_id,
            "claim_key": claim_key,
            "stage": stage,
            "message": message,
            "payload": payload or {},
        }

        with self._lock:
            try:
                with self.log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except Exception as exc:
                logger.error(f"trace log write failed: {exc}")

        if self.console_events:
            text = (
                f"[trace ms={rec['perf_ms']}]"
                f" doc={document_id or '-'}"
                f" claim={claim_key or '-'}"
                f" stage={stage or '-'}"
                f" event={event_type}"
                f" {message}"
            )
            logger.info(text)

        self._auto_scrape_counters(event_type, document_id, payload or {})
        self._auto_stage_progress(event_type, document_id, payload or {})

    def _auto_scrape_counters(self, event_type: str, document_id: str | None, payload: dict[str, Any]) -> None:
        if not document_id:
            return

        with self._lock:
            counters = self._doc_scrape.setdefault(
                document_id,
                {
                    "urls_discovered": 0,
                    "started": 0,
                    "done": 0,
                    "cache_hits": 0,
                    "failed": 0,
                },
            )

            if event_type == "retrieval_search_done":
                counters["urls_discovered"] += int(payload.get("num_urls", 0) or 0)
            elif event_type == "retrieval_page_fetch_start":
                counters["started"] += 1
            elif event_type == "retrieval_page_fetch_done":
                counters["done"] += 1
            elif event_type == "retrieval_page_cache_hit":
                counters["cache_hits"] += 1
                counters["done"] += 1
            elif event_type == "retrieval_page_fetch_error":
                counters["failed"] += 1
                counters["done"] += 1

    def get_document_scrape_snapshot(self, document_id: str) -> dict[str, int]:
        with self._lock:
            counters = self._doc_scrape.get(document_id)
            if not counters:
                return {
                    "urls_discovered": 0,
                    "started": 0,
                    "done": 0,
                    "cache_hits": 0,
                    "failed": 0,
                }
            return {
                "urls_discovered": int(counters.get("urls_discovered", 0)),
                "started": int(counters.get("started", 0)),
                "done": int(counters.get("done", 0)),
                "cache_hits": int(counters.get("cache_hits", 0)),
                "failed": int(counters.get("failed", 0)),
            }

    def _auto_stage_progress(self, event_type: str, document_id: str | None, payload: dict[str, Any]) -> None:
        if not (self.tqdm_enabled and document_id):
            return

        if event_type == "document_progress_start":
            total = int(payload.get("total_claims", 0) or 0)
            if total <= 0:
                return
            with self._lock:
                self._doc_totals[document_id] = total
                stage_bars = self._stage_bars.pop(document_id, {})
                for h in stage_bars.values():
                    try:
                        h.bar.close()
                    except Exception:
                        pass

                doc = document_id[:8]
                self._stage_bars[document_id] = {
                    "started": _ProgressHandle(tqdm(total=total, desc=f"doc:{doc} started", leave=True), total),
                    "scraping": _ProgressHandle(tqdm(total=1, desc=f"doc:{doc} scraping", leave=True), 1),
                    "retrieval": _ProgressHandle(tqdm(total=total, desc=f"doc:{doc} retrieval", leave=True), total),
                    "voting": _ProgressHandle(tqdm(total=total, desc=f"doc:{doc} voting", leave=True), total),
                    "completed": _ProgressHandle(tqdm(total=total, desc=f"doc:{doc} completed", leave=True), total),
                }
            return

        stage_map = {
            "claim_start": "started",
            "claim_retrieval_done": "retrieval",
            "claim_voting_done": "voting",
            "claim_done": "completed",
        }
        s = stage_map.get(event_type)
        if s:
            with self._lock:
                h = self._stage_bars.get(document_id, {}).get(s)
                if h:
                    h.bar.update(1)
                    h.completed += 1
                    h.bar.set_postfix_str(f"{h.completed}/{h.total}")
            return

        if event_type == "retrieval_search_done":
            discovered = int(payload.get("num_urls", 0) or 0)
            if discovered <= 0:
                return
            with self._lock:
                h = self._stage_bars.get(document_id, {}).get("scraping")
                if h:
                    h.total += discovered
                    h.bar.total = max(h.total, h.completed)
                    h.bar.set_postfix_str(f"{h.completed}/{h.total}")
                    h.bar.refresh()
            return

        if event_type in {"retrieval_page_cache_hit", "retrieval_page_fetch_done", "retrieval_page_fetch_error"}:
            with self._lock:
                h = self._stage_bars.get(document_id, {}).get("scraping")
                if h:
                    if h.completed >= h.total:
                        h.total = h.completed + 1
                        h.bar.total = h.total
                    h.bar.update(1)
                    h.completed += 1
                    h.bar.set_postfix_str(f"{h.completed}/{h.total}")
            return

        if event_type in {"audit_stream_done", "audit_stream_error", "document_progress_done"}:
            with self._lock:
                stage_bars = self._stage_bars.pop(document_id, {})
                for h in stage_bars.values():
                    try:
                        h.bar.close()
                    except Exception:
                        pass
                self._doc_totals.pop(document_id, None)
                self._doc_scrape.pop(document_id, None)

    def start_document_progress(self, document_id: str, total_claims: int) -> None:
        if not self.enabled:
            return

        with self._lock:
            self._doc_scrape[document_id] = {
                "urls_discovered": 0,
                "started": 0,
                "done": 0,
                "cache_hits": 0,
                "failed": 0,
            }

        if self.tqdm_enabled:
            with self._lock:
                prev = self._bars.pop(document_id, None)
                if prev:
                    try:
                        prev.bar.close()
                    except Exception:
                        pass
                bar = tqdm(total=total_claims, desc=f"doc:{document_id[:8]} claims", leave=True)
                self._bars[document_id] = _ProgressHandle(bar=bar, total=total_claims)

        self.event(
            "document_progress_start",
            document_id=document_id,
            stage="claims",
            message=f"tracking {total_claims} claims",
            payload={"total_claims": total_claims},
        )

    def update_document_progress(self, document_id: str, completed: int, total: int, status: str = "") -> None:
        if not self.enabled:
            return

        if self.tqdm_enabled:
            with self._lock:
                h = self._bars.get(document_id)
                if h:
                    delta = max(0, completed - h.completed)
                    if delta > 0:
                        h.bar.update(delta)
                        h.completed = completed
                    h.bar.set_postfix_str(f"{completed}/{total} {status}".strip())

        self.event(
            "document_progress_update",
            document_id=document_id,
            stage="claims",
            message=f"progress {completed}/{total}",
            payload={"completed": completed, "total": total, "status": status},
        )

    def finish_document_progress(self, document_id: str) -> None:
        if self.tqdm_enabled:
            with self._lock:
                h = self._bars.pop(document_id, None)
                if h:
                    try:
                        h.bar.close()
                    except Exception:
                        pass

        self.event("document_progress_done", document_id=document_id, stage="claims", message="done")


telemetry = RuntimeTelemetry()
