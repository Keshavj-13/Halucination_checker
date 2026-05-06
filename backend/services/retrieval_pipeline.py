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
from xml.etree import ElementTree

import httpx

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
from services.runtime_cache import JsonKVCache, stable_hash
from services.source_reliability import source_reliability_scorer
from services.telemetry import telemetry

logger = logging.getLogger("audit-api.retrieval")

REPORTED_PATTERNS = re.compile(
    r"\b(some people believe|some believe|it is claimed|the theory|reportedly|allegedly|is said to|according to|"
    r"rumor|unconfirmed|speculation|analysts say|commentators say|observers say|it appears|it seems|"
    r"is believed|is thought|purportedly|claims? that|suggests that|early reports?)\b"
)
REFUTE_PATTERNS = re.compile(
    r"\b(false|incorrect|debunked|no evidence|not true|myth|refute|refutes|refuted|contradict|contradicts|"
    r"contradicted|fabricated|unsupported|misleading|inaccurate|wrong|hoax|fake|denied|rebutted|"
    r"fails? to|cannot be verified|retracted|withdrawn|unfounded|baseless|counterevidence|counter-evidence)\b"
)
SUPPORT_PATTERNS = re.compile(
    r"\b(is|equals?|show(s|ed)?|demonstrate(s|d)?|confirm(s|ed)?|evidence indicates|measured|observed|"
    r"verified|validated|documented|recorded|official|published|peer reviewed|peer-reviewed|"
    r"data show(s|ed)?|study found|according to data|census|registry|public record|court record|"
    r"statistically significant|replicated|reproducible|corroborated)\b"
)

CLAIM_TYPE_TO_SOURCES: Dict[str, List[str]] = {
    "ENTITY_RELATION": ["wikidata", "wikipedia", "local"],
    "DATE_CLAIM": ["wikidata", "wikipedia", "local"],
    "NUMERIC_CLAIM": ["wikidata", "wikipedia", "local"],
    "SCIENTIFIC": ["pubmed", "arxiv", "openalex", "local"],
    "DEFINITION": ["wikipedia", "wikidata", "local"],
    "TEMPORAL": ["wikidata", "wikipedia", "local"],
    "SUBJECTIVE": ["local"],
    "UNVERIFIABLE": ["local"],
}


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text)


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p and len(p.strip()) >= 30]


def _infer_chunk_metadata(claim: str, snippet: str) -> Dict[str, Any]:
    claim_tokens = set(_tokenize(claim.lower()))
    snip_tokens = set(_tokenize(snippet.lower()))
    union = len(claim_tokens | snip_tokens)
    lexical = (len(claim_tokens & snip_tokens) / union) if union else 0.0

    lower = snippet.lower()
    quote = '"' in snippet or "“" in snippet or "”" in snippet
    reported = bool(REPORTED_PATTERNS.search(lower))
    refute_cue = bool(REFUTE_PATTERNS.search(lower))
    support_cue = bool(SUPPORT_PATTERNS.search(lower))

    stance = "mention"
    citation_direction = "none"
    attribution = "none"
    support = "weak"

    if quote:
        attribution = "quoted"
    elif reported:
        attribution = "reported"

    if reported:
        stance = "reported_belief"
        citation_direction = "reports"
    elif refute_cue and lexical >= 0.08:
        stance = "refute"
        citation_direction = "refutes"
        support = "contradicting"
    elif support_cue and lexical >= 0.10:
        stance = "support"
        citation_direction = "endorses"
        support = "supporting"
    elif quote and lexical >= 0.08:
        stance = "quotation"
        citation_direction = "reports"
    elif lexical >= 0.18:
        stance = "neutral"
    else:
        stance = "mention"

    return {
        "stance": stance,
        "attribution": attribution,
        "citation_direction": citation_direction,
        "support": support,
        "is_quote": quote,
        "is_reported_belief": reported,
    }


def _chunk_text_cpu(payload: Tuple[str, str, str, float, str, Dict[str, float], str]) -> List[Dict[str, Any]]:
    url, title, text, reliability, explanation, quality_signals, claim_text = payload
    tokens = _tokenize(text)
    if not tokens:
        return []

    chunks: List[Dict[str, Any]] = []
    sentences = _split_sentences(text)
    cursor = 0
    for sent in sentences:
        stoks = _tokenize(sent)
        if len(stoks) < 10:
            continue
        meta = _infer_chunk_metadata(claim_text, sent)
        chunks.append(
            {
                "title": title,
                "url": url,
                "snippet": sent,
                "support": meta["support"],
                "stance": meta["stance"],
                "attribution": meta["attribution"],
                "citation_direction": meta["citation_direction"],
                "is_quote": meta["is_quote"],
                "is_reported_belief": meta["is_reported_belief"],
                "bias_penalty": float(quality_signals.get("bias_penalty", 0.0)),
                "sponsorship_flag": bool(quality_signals.get("sponsorship_flag", 0.0) >= 0.5),
                "reliability_score": reliability,
                "reliability_explanation": explanation,
                "source_domain": urlparse(url).netloc,
                "chunk_start": cursor,
                "chunk_end": cursor + len(stoks),
                "page_quality_signals": quality_signals,
            }
        )
        cursor += len(stoks)
        if len(chunks) >= MAX_EVIDENCE_CHUNKS:
            break

    if not chunks and len(tokens) >= 12:
        snippet = " ".join(tokens[: min(180, len(tokens))])
        meta = _infer_chunk_metadata(claim_text, snippet)
        chunks.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "support": meta["support"],
                "stance": meta["stance"],
                "attribution": meta["attribution"],
                "citation_direction": meta["citation_direction"],
                "is_quote": meta["is_quote"],
                "is_reported_belief": meta["is_reported_belief"],
                "bias_penalty": float(quality_signals.get("bias_penalty", 0.0)),
                "sponsorship_flag": bool(quality_signals.get("sponsorship_flag", 0.0) >= 0.5),
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

    async def retrieve(
        self,
        claim: str,
        document_id: str = "unknown-document",
        claim_key: str = "",
        structured_claim: Dict[str, Any] | None = None,
        claim_type: str | None = None,
    ) -> RetrievalOutput:
        started = time.perf_counter()
        cache_hits = 0
        failures: List[str] = []

        telemetry.event("retrieval_start", document_id=document_id, claim_key=claim_key, stage="retrieval", message="retrieval started")

        typed_claim = (claim_type or (structured_claim or {}).get("claim_type") or "UNVERIFIABLE").upper()
        t0 = time.perf_counter()
        urls = self._build_typed_urls(claim, typed_claim)
        telemetry.event(
            "retrieval_search_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="retrieval.search",
            message=f"found {len(urls)} urls",
            payload={"runtime_ms": round((time.perf_counter() - t0) * 1000.0, 2), "num_urls": len(urls)},
        )
        tasks = [
            asyncio.create_task(self._fetch_and_extract(u, claim, typed_claim, document_id=document_id, claim_key=claim_key))
            for u in urls
        ]

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

        payloads: List[Tuple[str, str, str, float, str, Dict[str, float], str]] = []
        for i, (url, title, text, headers) in enumerate(pages):
            rel = source_reliability_scorer.score_page(
                url=url,
                title=title,
                text=text,
                claim_text=claim,
                headers=headers,
                cross_source_support=cross[i] if i < len(cross) else 0.0,
            )
            payloads.append((url, title, text, rel.score, rel.explanation, rel.signals, claim))

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

        telemetry.event(
            "retrieval_embedding_done",
            document_id=document_id,
            claim_key=claim_key,
            stage="retrieval.embed",
            message="embedding stage disabled for deterministic typed retrieval",
            payload={"runtime_ms": 0.0, "num_embeddings": 0},
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

    def _build_typed_urls(self, claim: str, claim_type: str) -> List[str]:
        key = stable_hash(f"typed::{claim_type}::{claim}")
        cached = self.search_cache.get(key)
        if cached:
            return cached[:MAX_SEARCH_RESULTS]

        q = "+".join(_tokenize(claim.lower())[:12])
        sources = CLAIM_TYPE_TO_SOURCES.get(claim_type, ["local"])
        urls: List[str] = []
        for src in sources:
            if src == "wikidata":
                urls.append(f"https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&search={q}")
            elif src == "wikipedia":
                urls.append(f"https://en.wikipedia.org/api/rest_v1/page/summary/{q}")
            elif src == "pubmed":
                urls.append(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmax=3&retmode=json&term={q}")
            elif src == "arxiv":
                urls.append(f"https://export.arxiv.org/api/query?search_query=all:{q}&start=0&max_results=3")
            elif src == "openalex":
                urls.append(f"https://api.openalex.org/works?search={q}&per-page=3")
            elif src == "local":
                urls.append(f"local://corpus?query={q}")

        deduped = []
        seen = set()
        for u in urls:
            if u in seen:
                continue
            seen.add(u)
            deduped.append(u)
            if len(deduped) >= MAX_SEARCH_RESULTS:
                break

        self.search_cache.set(key, deduped)
        return deduped

    async def _fetch_and_extract(
        self,
        url: str,
        claim_text: str,
        claim_type: str,
        document_id: str = "unknown-document",
        claim_key: str = "",
    ) -> Tuple[str, str, str, Dict[str, str], bool]:
        if url.startswith("local://"):
            title, text = self._local_corpus_extract(claim_text)
            return url, title, text, {"content-type": "text/plain", "x-source-type": "local"}, True

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
            try:
                resp = await self._http_client.get(url)
                resp.raise_for_status()
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

            title, text = self._parse_typed_source(url, resp.text, claim_type)
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

    def _parse_typed_source(self, url: str, payload: str, claim_type: str) -> Tuple[str, str]:
        try:
            if "wikidata.org/w/api.php" in url:
                data = json.loads(payload)
                items = data.get("search", [])[:3]
                text = " ".join(f"{it.get('label', '')}: {it.get('description', '')}" for it in items)
                return "Wikidata", text[:25000]

            if "wikipedia.org/api/rest_v1/page/summary" in url:
                data = json.loads(payload)
                title = data.get("title") or "Wikipedia"
                text = data.get("extract") or ""
                return title, text[:25000]

            if "ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi" in url:
                data = json.loads(payload)
                ids = data.get("esearchresult", {}).get("idlist", [])
                text = f"PubMed candidate ids for claim type {claim_type}: {', '.join(ids[:3])}"
                return "PubMed", text

            if "export.arxiv.org/api/query" in url:
                root = ElementTree.fromstring(payload)
                ns = {"a": "http://www.w3.org/2005/Atom"}
                entries = root.findall("a:entry", ns)[:3]
                parts = []
                for e in entries:
                    title = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
                    summary = (e.findtext("a:summary", default="", namespaces=ns) or "").strip()
                    parts.append(f"{title}. {summary}")
                return "arXiv", " ".join(parts)[:25000]

            if "api.openalex.org/works" in url:
                data = json.loads(payload)
                results = data.get("results", [])[:3]
                parts = []
                for r in results:
                    title = r.get("display_name", "")
                    abstract = r.get("abstract_inverted_index") or {}
                    tokens = sorted(((idx, tok) for tok, arr in abstract.items() for idx in arr), key=lambda x: x[0])
                    abs_text = " ".join(tok for _, tok in tokens[:120])
                    parts.append(f"{title}. {abs_text}")
                return "OpenAlex", " ".join(parts)[:25000]
        except Exception:
            pass

        cleaned = re.sub(r"\s+", " ", payload or "").strip()
        return "Typed Source", cleaned[:25000]

    def _local_corpus_extract(self, claim: str) -> Tuple[str, str]:
        candidates: List[str] = []
        for p in [
            SEARCH_CACHE_PATH,
        ]:
            if p.exists():
                try:
                    candidates.append(p.read_text(encoding="utf-8")[:20000])
                except Exception:
                    continue
        if not candidates:
            return "Local Corpus", claim

        claim_tokens = set(_tokenize(claim.lower()))
        best = ""
        best_score = -1
        for c in candidates:
            score = len(claim_tokens & set(_tokenize(c.lower())))
            if score > best_score:
                best_score = score
                best = c
        return "Local Corpus", re.sub(r"\s+", " ", best).strip()[:25000]

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
