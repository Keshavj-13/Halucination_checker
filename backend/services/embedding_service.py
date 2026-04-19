from __future__ import annotations

import asyncio
import logging
from typing import List

import httpx

from services.config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MAX_IN_FLIGHT,
    EMBEDDING_MODEL,
    EMBEDDING_TIMEOUT_SECONDS,
    EMBEDDING_USE_BATCH_ENDPOINT,
    EMBEDDING_URL,
    OLLAMA_NUM_GPU,
    OLLAMA_NUM_THREAD,
)
from services.runtime_cache import JsonKVCache, stable_hash
from services.config import EMBEDDING_CACHE_PATH

logger = logging.getLogger("audit-api.embedding")


class EmbeddingService:
    def __init__(self):
        self.base_url = EMBEDDING_URL
        self.model = EMBEDDING_MODEL
        self.cache = JsonKVCache(EMBEDDING_CACHE_PATH)
        self._sem = asyncio.Semaphore(EMBEDDING_MAX_IN_FLIGHT)
        self._client = httpx.AsyncClient(timeout=max(EMBEDDING_TIMEOUT_SECONDS, 8.0))
        self._batch_url = self.base_url.replace("/embeddings", "/embed") if EMBEDDING_USE_BATCH_ENDPOINT else ""

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed_text(self, text: str) -> List[float]:
        rows = await self.embed_many([text])
        return rows[0] if rows else []

    async def embed_many(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        key_prefix = f"{self.model}::"
        out: List[List[float] | None] = [None] * len(texts)
        pending = []

        for i, t in enumerate(texts):
            norm = (t or "")[:4000]
            k = stable_hash(key_prefix + norm)
            cached = self.cache.get(k)
            if cached:
                out[i] = cached
            else:
                pending.append((i, norm, k))

        if pending:
            batch_size = EMBEDDING_BATCH_SIZE
            tasks = []
            for i in range(0, len(pending), batch_size):
                batch = pending[i : i + batch_size]
                tasks.append(asyncio.create_task(self._embed_batch(batch)))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    logger.warning(f"Embedding batch failed: {res}")
                    continue
                for idx, emb in res:
                    out[idx] = emb

        return [row if row is not None else [] for row in out]

    async def _embed_batch(self, batch):
        async with self._sem:
            inputs = [text for _, text, _ in batch]

            payload = {
                "model": self.model,
                "input": inputs,
                "options": {
                    "num_gpu": OLLAMA_NUM_GPU,
                    "num_thread": OLLAMA_NUM_THREAD,
                },
            }

            vectors = []
            if self._batch_url:
                try:
                    resp = await self._client.post(self._batch_url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    vectors = data.get("embeddings") or []
                except Exception as exc:
                    logger.warning(f"Batch embed endpoint failed: {exc}")

            if not vectors:
                vectors = await self._fallback_single(inputs)

            rows = []
            for (idx, _, cache_key), emb in zip(batch, vectors):
                emb = emb or []
                if emb:
                    self.cache.set(cache_key, emb)
                rows.append((idx, emb))

            if len(rows) < len(batch):
                missing = batch[len(rows) :]
                rows.extend([(idx, []) for idx, _, _ in missing])

            return rows

    async def _fallback_single(self, inputs: List[str]) -> List[List[float]]:
        results: List[List[float]] = []
        for t in inputs:
            try:
                resp = await self._client.post(
                    self.base_url,
                    json={
                        "model": self.model,
                        "prompt": t,
                    },
                )
                resp.raise_for_status()
                results.append(resp.json().get("embedding", []))
            except Exception as exc:
                logger.warning(f"Single embed fallback failed: {exc}")
                results.append([])
        return results


embedding_service = EmbeddingService()
