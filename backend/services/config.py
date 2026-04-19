from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MODELS_DIR = DATA_DIR / "models"
LOGS_DIR = DATA_DIR / "logs"
CACHE_DIR = DATA_DIR / "cache"

for _dir in (RAW_DATA_DIR, PROCESSED_DATA_DIR, MODELS_DIR, LOGS_DIR, CACHE_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

CPU_COUNT = os.cpu_count() or 4
DEFAULT_CPU_WORKERS = max(1, CPU_COUNT - 1)
CPU_WORKERS = int(os.getenv("CPU_WORKERS", str(DEFAULT_CPU_WORKERS)))
CPU_WORKERS = max(1, min(CPU_WORKERS, CPU_COUNT))
VOTER_CPU_WORKERS = int(os.getenv("VOTER_CPU_WORKERS", str(min(16, CPU_WORKERS * 2))))
VOTER_CPU_WORKERS = max(1, min(VOTER_CPU_WORKERS, max(4, CPU_COUNT * 2)))

MAX_CLAIMS_IN_FLIGHT = int(os.getenv("MAX_CLAIMS_IN_FLIGHT", str(min(12, CPU_WORKERS * 2))))
MAX_CLAIMS_IN_FLIGHT = max(1, min(MAX_CLAIMS_IN_FLIGHT, max(4, CPU_COUNT * 3)))

MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "5"))
MAX_EVIDENCE_CHUNKS = int(os.getenv("MAX_EVIDENCE_CHUNKS", "12"))
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
SCRAPE_CONCURRENCY = int(os.getenv("SCRAPE_CONCURRENCY", str(min(16, CPU_WORKERS * 2))))
SCRAPE_CONCURRENCY = max(1, min(SCRAPE_CONCURRENCY, max(4, CPU_COUNT * 2)))
RETRIEVAL_DEADLINE_SECONDS = float(os.getenv("RETRIEVAL_DEADLINE_SECONDS", "2.8"))
MAX_PAGES_TO_PROCESS = int(os.getenv("MAX_PAGES_TO_PROCESS", "3"))
CLAIM_PIPELINE_DEADLINE_SECONDS = float(os.getenv("CLAIM_PIPELINE_DEADLINE_SECONDS", "8.0"))
VOTING_TIMEOUT_SECONDS = float(os.getenv("VOTING_TIMEOUT_SECONDS", "10.0"))
RETRIEVAL_STAGE_TIMEOUT_SECONDS = float(os.getenv("RETRIEVAL_STAGE_TIMEOUT_SECONDS", "12.0"))
VOTER_TIMEOUT_SECONDS = float(os.getenv("VOTER_TIMEOUT_SECONDS", "6.0"))

LLM_VOTER_ENABLED = os.getenv("LLM_VOTER_ENABLED", "false").lower() == "true"
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "8.0"))

EMBEDDING_TIMEOUT_SECONDS = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "3.0"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))
EMBEDDING_BATCH_SIZE = max(1, min(EMBEDDING_BATCH_SIZE, 128))
EMBEDDING_MAX_IN_FLIGHT = int(os.getenv("EMBEDDING_MAX_IN_FLIGHT", "24"))
EMBEDDING_MAX_IN_FLIGHT = max(1, min(EMBEDDING_MAX_IN_FLIGHT, 64))
EMBEDDING_USE_BATCH_ENDPOINT = os.getenv("EMBEDDING_USE_BATCH_ENDPOINT", "false").lower() == "true"

OLLAMA_NUM_GPU = int(os.getenv("OLLAMA_NUM_GPU", "-1"))
OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", str(CPU_WORKERS)))
OLLAMA_NUM_THREAD = max(1, min(OLLAMA_NUM_THREAD, CPU_COUNT))

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
EMBEDDING_URL = os.getenv("EMBEDDING_URL", f"{OLLAMA_BASE_URL}/api/embeddings" if OLLAMA_BASE_URL else "http://127.0.0.1/api/embeddings")

CONSISTENCY_MODEL_PATH = MODELS_DIR / "consistency_model.joblib"
CALIBRATOR_MODEL_PATH = MODELS_DIR / "calibrator.joblib"

RUNTIME_LOG_PATH = LOGS_DIR / "audit_claim_logs.jsonl"
TRACE_LOG_PATH = LOGS_DIR / "runtime_trace.jsonl"
SEARCH_CACHE_PATH = CACHE_DIR / "search_cache.json"
PAGE_CACHE_DIR = CACHE_DIR / "pages"
EMBEDDING_CACHE_PATH = CACHE_DIR / "embedding_cache.json"
PAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

TRACE_ENABLED = os.getenv("TRACE_ENABLED", "true").lower() == "true"
TRACE_CONSOLE_EVENTS = os.getenv("TRACE_CONSOLE_EVENTS", "true").lower() == "true"
TRACE_TQDM_ENABLED = os.getenv("TRACE_TQDM_ENABLED", "true").lower() == "true"
PIPELINE_SERIAL_MODE = os.getenv("PIPELINE_SERIAL_MODE", "false").lower() == "true"
PIPELINE_PROCESS_MODE = os.getenv("PIPELINE_PROCESS_MODE", "false").lower() == "true"
CLAIM_PROCESS_WORKERS = int(os.getenv("CLAIM_PROCESS_WORKERS", "2"))
CLAIM_PROCESS_WORKERS = max(1, min(CLAIM_PROCESS_WORKERS, max(2, CPU_COUNT)))
VOTERS_SERIAL_MODE = os.getenv("VOTERS_SERIAL_MODE", "false").lower() == "true"
CONSENSUS_USE_CALIBRATOR = os.getenv("CONSENSUS_USE_CALIBRATOR", "false").lower() == "true"
