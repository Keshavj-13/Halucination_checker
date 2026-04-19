from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from models.schemas import Evidence
from services.config import (
    CPU_WORKERS,
    HTTP_TIMEOUT_SECONDS,
    MAX_EVIDENCE_CHUNKS,
    MAX_PAGES_TO_PROCESS,
    MAX_SEARCH_RESULTS,
    PAGE_CACHE_DIR,
    RETRIEVAL_DEADLINE_SECONDS,
    SCRAPE_CONCURRENCY,
    SEARCH_CACHE_PATH,
)
from services.evidence_clusterer import clusterer
from services.embedding_service import embedding_service
from services.runtime_cache import JsonKVCache, stable_hash
from services.source_reliability import source_reliability_scorer
from services.telemetry import telemetry

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover
    from duckduckgo_search import DDGS

logger = logging.getLogger("audit-api.retrieval")


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text)


def _chunk_text_cpu(payload: Tuple[str, str, str, float, str, Dict[str, float]]) -> List[Dict[str, Any]]:
    url, title, text, reliability, explanation, quality_signals = payload
    tokens = _tokenize(text)
    if not tokens:
        return []

    chunks: List[Dict[str, Any]] = []
    window, stride = 280, 220
    for i in range(0, len(tokens), stride):
        chunk_tokens = tokens[i : i + window]
        if len(chunk_tokens) < 20:
            continue
        chunks.append(
            {
                "title": title,
                "url": url,
                "snippet": " ".join(chunk_tokens),
                "support": "weak",
                "reliability_score": reliability,
                "reliability_explanation": explanation,
                "source_domain": urlparse(url).netloc,
                "chunk_start": i,
                "chunk_end": min(i + window, len(tokens)),
                "page_quality_signals": quality_signals,
            }
        )
        if len(chunks) >= MAX_EVIDENCE_CHUNKS:
            break

    if not chunks and len(tokens) >= 12:
        chunks.append(
            {
                "title": title,
                "url": url,
                "snippet": " ".join(tokens[: min(180, len(tokens))]),
                "support": "weak",
                "reliability_score": reliability,
                "reliability_explanation": explanation,
                "source_domain": urlparse(url).netloc,
                "chunk_start": 0,
                "chunk_end": min(180, len(tokens)),
                "page_quality_signals": quality_signals,
            }
        )
    return chunks


@dataclass
class RetrievalOutput:
    evidence: List[Evidence]
    urls: List[str]
    runtime_ms: float
    cache_hits: int
    failures: List[str]
    num_clusters: int = 0
    independent_clusters: int = 0
    cluster_support: float = 0.0


class RetrievalPipeline:
    def __init__(self):
        self.search_cache = JsonKVCache(SEARCH_CACHE_PATH)
        self._sem = asyncio.Semaphore(SCRAPE_CONCURRENCY)
        self._cpu_pool = ThreadPoolExecutor(max_workers=CPU_WORKERS)
        self._http_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True)

    async def aclose(self) -> None:
        await self._http_client.aclose()

    async def retrieve(self, claim: str, document_id: str = "unknown-document", claim_key: str = "") -> RetrievalOutput:
        started = time.perf_counter()
        cache_hits = 0
        failures: List[str] = []

        telemetry.event("retrieval_start", document_id=document_id, claim_key=claim_key, stage="retrieval", message="retrieval started")

        t0 = time.perf_counter()
        urls = await self._search_urls(claim)
        telemetry.event(
            "retrieval_search_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="retrieval.search",
            message=f"found {len(urls)} urls",
            payload={"runtime_ms": round((time.perf_counter() - t0) * 1000.0, 2), "num_urls": len(urls)},
        )
        tasks = [asyncio.create_task(self._fetch_and_extract(u, document_id=document_id, claim_key=claim_key)) for u in urls]

        valid_pages: List[Tuple[str, str, str, Dict[str, str]]] = []
        deadline = time.perf_counter() + RETRIEVAL_DEADLINE_SECONDS
        t1 = time.perf_counter()
        try:
            for task in asyncio.as_completed(tasks, timeout=max(RETRIEVAL_DEADLINE_SECONDS, 0.5)):
                if time.perf_counter() >= deadline:
                    break
                try:
                    result = await task
                except Exception as exc:
                    failures.append(str(exc))
                    continue
                url, title, text, headers, from_cache = result
                cache_hits += int(from_cache)
                if text:
                    valid_pages.append((url, title, text, headers))
                if len(valid_pages) >= MAX_PAGES_TO_PROCESS:
                    break
        except TimeoutError:
            failures.append("retrieval deadline reached")

        if not valid_pages:
            telemetry.event(
                "retrieval_rescue_wait_start",
                document_id=document_id,
                claim_key=claim_key,
                stage="retrieval.fetch",
                message="no valid pages yet; waiting for first page",
                payload={"pending_tasks": sum(1 for t in tasks if not t.done())},
            )
            pending = {t for t in tasks if not t.done()}
            if pending:
                done_once, _ = await asyncio.wait(
                    pending,
                    timeout=max(HTTP_TIMEOUT_SECONDS, 2.5),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done_once:
                    try:
                        result = await task
                    except Exception as exc:
                        failures.append(str(exc))
                        continue
                    url, title, text, headers, from_cache = result
                    cache_hits += int(from_cache)
                    if text:
                        valid_pages.append((url, title, text, headers))
                        break

        telemetry.event(
            "retrieval_fetch_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="retrieval.fetch",
            message=f"fetched {len(valid_pages)} valid pages",
            payload={"runtime_ms": round((time.perf_counter() - t1) * 1000.0, 2), "num_pages": len(valid_pages), "cache_hits": cache_hits},
        )

        for t in tasks:
            if not t.done():
                t.cancel()

        pages = self._dedupe_pages(valid_pages)
        cross = source_reliability_scorer.estimate_cross_source_support([p[2] for p in pages])

        payloads: List[Tuple[str, str, str, float, str, Dict[str, float]]] = []
        for i, (url, title, text, headers) in enumerate(pages):
            rel = source_reliability_scorer.score_page(
                url=url,
                title=title,
                text=text,
                claim_text=claim,
                headers=headers,
                cross_source_support=cross[i] if i < len(cross) else 0.0,
            )
            payloads.append((url, title, text, rel.score, rel.explanation, rel.signals))

        t2 = time.perf_counter()
        loop = asyncio.get_running_loop()
        jobs = [loop.run_in_executor(self._cpu_pool, _chunk_text_cpu, p) for p in payloads]
        chunk_batches = await asyncio.gather(*jobs, return_exceptions=True)

        evidence: List[Evidence] = []
        for batch in chunk_batches:
            if isinstance(batch, Exception):
                failures.append(str(batch))
                continue
            for chunk in batch:
                evidence.append(Evidence(**chunk))
        telemetry.event(
            "retrieval_chunk_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="retrieval.chunk",
            message=f"chunked into {len(evidence)} evidence snippets",
            payload={"runtime_ms": round((time.perf_counter() - t2) * 1000.0, 2), "num_chunks": len(evidence)},
        )

        t3 = time.perf_counter()
        embs = await embedding_service.embed_many([ev.snippet for ev in evidence])
        for ev, emb in zip(evidence, embs):
            if emb:
                ev.embedding = emb
        telemetry.event(
            "retrieval_embedding_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="retrieval.embed",
            message="embeddings ready",
            payload={"runtime_ms": round((time.perf_counter() - t3) * 1000.0, 2), "num_embeddings": sum(1 for e in embs if e)},
        )

        t4 = time.perf_counter()
        evidence = clusterer.assign_clusters(evidence)
        summary = clusterer.summarize(evidence)
        telemetry.event(
            "retrieval_cluster_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="retrieval.cluster",
            message="clusters assigned",
            payload={
                "runtime_ms": round((time.perf_counter() - t4) * 1000.0, 2),
                "num_clusters": summary.num_clusters,
                "independent_clusters": summary.independent_clusters,
                "support_score": summary.support_score,
            },
        )

        runtime_ms = (time.perf_counter() - started) * 1000.0
        evidence = evidence[:MAX_EVIDENCE_CHUNKS]
        telemetry.event(
            "retrieval_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="retrieval",
            message="retrieval completed",
            payload={"runtime_ms": round(runtime_ms, 2), "num_urls": len(urls), "num_chunks": len(evidence), "failures": failures},
        )
        return RetrievalOutput(
            evidence=evidence,
            urls=urls,
            runtime_ms=runtime_ms,
            cache_hits=cache_hits,
            failures=failures,
            num_clusters=summary.num_clusters,
            independent_clusters=summary.independent_clusters,
            cluster_support=summary.support_score,
        )

    async def _search_urls(self, claim: str) -> List[str]:
        key = stable_hash(f"ddg::{claim}")
        cached = self.search_cache.get(key)
        if cached:
            return cached[:MAX_SEARCH_RESULTS]

        loop = asyncio.get_running_loop()

        def _sync() -> List[str]:
            with DDGS() as ddgs:
                rows = list(ddgs.text(claim, max_results=MAX_SEARCH_RESULTS))
            return [r.get("href") for r in rows if r.get("href")]

        try:
            urls = await asyncio.wait_for(
                loop.run_in_executor(None, _sync),
                timeout=max(HTTP_TIMEOUT_SECONDS, 3.0),
            )
        except Exception as exc:
            logger.warning(f"Search failed/timeout for claim: {claim[:60]}... ({exc})")
            urls = []

        if not urls:
            simplified = " ".join(re.findall(r"[a-zA-Z0-9]+", claim.lower())[:12]).strip()
            if simplified and simplified != claim.lower().strip():
                try:
                    telemetry.event(
                        "retrieval_search_retry",
                        stage="retrieval.search",
                        message="retry with simplified query",
                        payload={"query": simplified},
                    )

                    def _sync_retry() -> List[str]:
                        with DDGS() as ddgs:
                            rows = list(ddgs.text(simplified, max_results=MAX_SEARCH_RESULTS))
                        return [r.get("href") for r in rows if r.get("href")]

                    urls = await asyncio.wait_for(
                        loop.run_in_executor(None, _sync_retry),
                        timeout=max(HTTP_TIMEOUT_SECONDS, 3.0),
                    )
                except Exception:
                    urls = []

        self.search_cache.set(key, urls)
        return urls

    async def _fetch_and_extract(self, url: str, document_id: str = "unknown-document", claim_key: str = "") -> Tuple[str, str, str, Dict[str, str], bool]:
        page_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        cache_file = PAGE_CACHE_DIR / f"{page_key}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            telemetry.event(
                "retrieval_page_cache_hit",
                document_id=document_id,
                claim_key=claim_key,
                stage="retrieval.fetch",
                message="page cache hit",
                payload={"url": url},
            )
            return url, data.get("title", "Web Source"), data.get("text", ""), data.get("headers", {}), True

        telemetry.event(
            "retrieval_page_fetch_start",
            document_id=document_id,
            claim_key=claim_key,
            stage="retrieval.fetch",
            message="page fetch started",
            payload={"url": url},
        )
        async with self._sem:
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            }
            try:
                resp = await self._http_client.get(url, headers=headers)
                resp.raise_for_status()
                html = resp.text
            except Exception as exc:
                telemetry.event(
                    "retrieval_page_fetch_error",
                    document_id=document_id,
                    claim_key=claim_key,
                    stage="retrieval.fetch",
                    message=str(exc),
                    payload={"url": url},
                )
                raise

        title, text = self._extract_main_text(html)
        data = {
            "title": title,
            "text": text,
            "headers": {k.lower(): v for k, v in resp.headers.items()},
        }
        cache_file.write_text(json.dumps(data), encoding="utf-8")
        telemetry.event(
            "retrieval_page_fetch_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="retrieval.fetch",
            message="page fetch completed",
            payload={"url": url, "chars": len(text)},
        )
        return url, title, text, data["headers"], False

    def _extract_main_text(self, html: str) -> Tuple[str, str]:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript", "footer", "nav", "aside"]):
            tag.decompose()
        title = soup.title.get_text(strip=True) if soup.title else "Web Source"
        article = soup.find("article")
        body = article if article else soup.body
        text = body.get_text(" ", strip=True) if body else soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        return title, text[:25000]

    def _dedupe_pages(self, pages: List[Tuple[str, str, str, Dict[str, str]]]) -> List[Tuple[str, str, str, Dict[str, str]]]:
        unique = []
        seen = set()
        for page in pages:
            sig = stable_hash(" ".join(_tokenize(page[2])[:300]))
            if sig in seen:
                continue
            seen.add(sig)
            unique.append(page)
        return unique


retrieval_pipeline = RetrievalPipeline()
