# SAMSA Checker (Hallucination Audit System)

Full-stack document hallucination auditing system with:

- claim extraction
- retrieval + evidence scoring
- multi-voter verification
- live streaming progress
- document upload text extraction
- local SQLite accounts + audit history
- authenticated chat history API

## Tech Stack

- **Backend:** FastAPI
- **Frontend:** React + Vite + Tailwind
- **Storage:** local SQLite (`backend/data/app_state.db`) + JSON/JSONL cache/log files in `data/`
- **Retrieval:** DuckDuckGo + page scraping + chunking + clustering
- **Verification:** heuristic, semantic, entity, consistency, deterministic (non-LLM)

## Repository Layout

- `backend/` API server, routes, verification pipeline
- `frontend/` React app
- `data/` shared runtime/cache/model/log directories
- `start.sh` one-command local startup (backend + frontend)

## Features

- **Atomic claim extraction** with start/end offsets
- **Async retrieval + scraping** with evidence chunking and clustering
- **Expanded keyword banks** for stance, relation, retrieval, reliability, and vibe scoring
- **Large website prior/penalty maps** (high-trust and low-trust domains)
- **Multi-factor source reliability** with quality, sponsorship, advocacy, spam, and vibe-aware signals
- **Five-voter deterministic ensemble** (heuristic, semantic, entity, consistency, deterministic)
- **Consensus scoring** for `Verified`, `Plausible`, and `Hallucination`
- **Live streaming progress** via SSE (claim-by-claim updates)
- **Document upload + text extraction** (`pdf`, `docx`, `pptx`, and text formats)
- **Local account system** (register/login/logout with SQLite sessions)
- **Per-user audit history** with reopen support in UI
- **Authenticated chat + chat history** persistence by session
- **Trace logs + runtime logs** for debugging and tuning
- **Trusted Knowledge First layer**: authoritative domain check before web retrieval

## Deterministic Non-LLM Decision System

The audit decision path is deterministic and non-LLM by default. LLM is not used as a voter in claim verification.

### Evidence Evaluation Unit

Treat each evidence chunk as a structured unit:

- `stance`: `+1 | 0 | -1`
- `relation_match`: `0..1`
- `entity_match`: `0..1`
- `numeric_match`: `0..1`
- `reliability`: `0..1`
- `bias_penalty`: `0..1`

### Contribution Formula

Use strict relation-aware scoring:

```python
effective_reliability = reliability * (1 - bias_penalty)

evidence_strength = (
  stance
  * effective_reliability
  * relation_match
  * (0.5 + 0.5 * entity_match)
  * (0.5 + 0.5 * numeric_match)
)
```

Aggregation:

```python
support = sum(max(0, evidence_strength))
refute  = sum(abs(min(0, evidence_strength)))
```

Decision:

```python
if support + refute == 0:
  label = "Uncertain"
elif support > 2 * refute:
  label = "Verified"
elif refute > 2 * support:
  label = "Hallucination"
else:
  label = "Conflicting"
```

### Hard Constraints

1. **Direct evidence requirement for verification**
   - at least 2 independent high-reliability sources
   - and `relation_match > 0.7`

2. **Strong refutation override**
   - if a high-trust source strongly refutes the claim, force `Hallucination`

3. **Missing evidence rule**
   - if no strong evidence exists, return `Uncertain` (not `Hallucination`)

4. **Low reliability cutoff**
   - ignore evidence when `reliability < 0.3`

5. **Bias adjustment**
   - reduce influence for interested/funded sources (e.g. halve effective reliability)

### Required Deterministic Layers

1. Stance classification
2. Relation matching (relation-level alignment, not topic similarity)
3. Numeric reasoning (unit normalization + ~5% tolerance)
4. Source reliability
5. Contradiction dominance
6. Bias penalties

### Practical Notes

- Keep clustering as auxiliary evidence quality signal, not a primary decision signal.
- Prioritize explicit contradiction and relation mismatch penalties over semantic similarity.
- For technical claims, add checks for definition/API correctness and unit consistency.
- Retrieval and reliability modules use expanded lexicons (support/refute/neutral cues, relation cue families, spam/sponsorship/advocacy/factual/hype vibe patterns).

## Trusted Knowledge First Verification Layer

Implemented in [backend/services/trusted_verifier.py](backend/services/trusted_verifier.py).

Pipeline order:

1. Parse claim (entities, relation, numbers, units, domain)
2. Route to trusted domain-aware checks
3. Short-circuit when authoritative trusted verdict is definitive
4. Only then use web retrieval fallback if trusted data is insufficient

Current behavior includes:

- domain classification (physics, medicine, mathematics, computer science, engineering, economics, history, geography, law, fashion, culture, etc.)
- authoritative source mapping by domain
- numeric normalization and tolerance checks (including scientific notation)
- trusted contradiction override
- trusted evidence seeding into fallback retrieval path
- major-source verified path can return full-confidence trusted verdict

## Core Features

### Audit Pipeline

1. Atomic claim extraction with character offsets
2. Parallel retrieval + scraping + chunking
3. Source reliability + bias/sponsorship signals
4. Evidence clustering and support signals
5. Multi-voter deterministic consensus (`Verified` / `Plausible` / `Hallucination`)
6. Streaming claim-by-claim updates over SSE

### UI/UX

- live claim progress and status updates
- evidence/detail panel
- drag/drop or upload files (`pdf`, `docx`, `pptx`, text formats)
- account login/register flow
- persistent audit history sidebar

### Accounts + History + Chat

- local SQLite auth (register/login/logout)
- per-user audit history persistence
- authenticated chat endpoint with per-session chat history persistence

## Quick Start

### 1) Configure environment

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` as needed.

### 2) Start everything (recommended)

From project root:

```bash
./start.sh
```

This script:

- loads `backend/.env`
- installs backend requirements (if needed)
- starts backend on configured/fallback port
- installs frontend dependencies if missing
- starts Vite with `VITE_API_BASE` pointed to backend

## Manual Run

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

Alternative backend launcher (auto port handling + worker env export):

```bash
cd backend
./run_backend.sh
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## API Overview

### Health

- `GET /`
- `GET /health`

### Audit

- `POST /audit` (JSON response)
- `POST /audit/stream` (SSE stream)
- `GET /audit/sample`
- `POST /audit/probe` (diagnostic subset probe)

### Documents

- `POST /documents/readable-text`
  - multipart upload
  - returns extracted text + metadata

### Auth + Audit History

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/logout`
- `GET /history`
- `GET /history/{history_id}`

### Chat (authenticated)

- `POST /chat`
- `GET /chat/history/{session_id}`

> Send `Authorization: Bearer <token>` for all protected endpoints.

## Local Database

Schema file: `backend/sql/init_app_state.sql`

Tables:

- `users`
- `sessions`
- `audit_history`
- `chat_history`

The backend initializes schema automatically via `AuthStore`.

Default seeded admin credentials (override via env):

- `SAMSA_ADMIN_USERNAME` (default: `admin`)
- `SAMSA_ADMIN_PASSWORD` (default: `Admin@Samsa2026!`)

## Configuration (`backend/.env`)

Important knobs (non-exhaustive):

### Network / ports

- `BACKEND_PORT_START`
- `BACKEND_PORT_FALLBACK_START`

### Retrieval / throughput

- `MAX_SEARCH_RESULTS`
- `MAX_EVIDENCE_CHUNKS`
- `SCRAPE_CONCURRENCY`
- `MAX_PAGES_TO_PROCESS`
- `HTTP_TIMEOUT_SECONDS`
- `RETRIEVAL_DEADLINE_SECONDS`
- `CLAIM_PIPELINE_DEADLINE_SECONDS`
- `RETRIEVAL_STAGE_TIMEOUT_SECONDS`
- `VOTER_TIMEOUT_SECONDS`

### Concurrency

- `CPU_WORKERS`
- `VOTER_CPU_WORKERS`
- `MAX_CLAIMS_IN_FLIGHT`
- `PIPELINE_SERIAL_MODE`
- `PIPELINE_PROCESS_MODE`
- `CLAIM_PROCESS_WORKERS`
- `VOTERS_SERIAL_MODE`

### LLM / embedding

- `LLM_PROVIDER`
- `GEMINI_API_KEY`
- `LLM_MODEL`
- `LLM_TIMEOUT_SECONDS`
- `LLM_VOTER_ENABLED` (legacy config; audit voter path is deterministic)
- `OLLAMA_BASE_URL`
- `EMBEDDING_URL`
- `EMBEDDING_MODEL`
- `EMBEDDING_TIMEOUT_SECONDS`
- `EMBEDDING_BATCH_SIZE`
- `EMBEDDING_MAX_IN_FLIGHT`
- `EMBEDDING_USE_BATCH_ENDPOINT`
- `OLLAMA_NUM_GPU`
- `OLLAMA_NUM_THREAD`

### Tracing

- `TRACE_ENABLED`
- `TRACE_CONSOLE_EVENTS`
- `TRACE_TQDM_ENABLED`

### Consensus

- `CONSENSUS_USE_CALIBRATOR`

## Runtime Data Paths

Under `data/`:

- `cache/search_cache.json`
- `cache/embedding_cache.json`
- `cache/pages/*.json`
- `logs/audit_claim_logs.jsonl`
- `logs/runtime_trace.jsonl`
- `models/*.joblib`

## Dependencies

Backend dependencies are in `backend/requirements.txt`.

Notable packages:

- `fastapi`, `uvicorn`, `httpx`, `scikit-learn`, `duckduckgo-search`, `ddgs`, `beautifulsoup4`, `lxml`, `tqdm`
- upload parsing: `PyPDF2`, `python-docx`, `python-pptx`, `python-multipart`

Frontend dependencies are in `frontend/package.json`.

## Legacy Notes (kept for continuity)

### Cumulative Multilayer Ensemble Auditor

The backend uses a modular multilayer stack with deterministic logging and calibration hooks:

1. Atomic claim decomposition with character offsets
2. Async retrieval pipeline (DuckDuckGo, concurrent scraping, chunking)
3. Multi-factor source reliability (domain, quality, freshness, cross-source support, spam penalty)
4. Evidence clustering signal (auxiliary support confidence from independent clusters)
5. Ensemble voters:
  - Heuristic TF-IDF voter
  - Semantic embedding voter
  - Entity/date/number voter
  - Lightweight consistency model voter
  - Deterministic relation/stance/numeric voter
6. Calibrated consensus engine (meta-classifier when enabled)
7. Per-claim pipeline deadline guard
8. JSONL logging for every claim in `data/logs/audit_claim_logs.jsonl`

### Data Layout

- `data/raw` downloaded datasets
- `data/processed` cleaned training/eval rows
- `data/models` trained classifier and calibrator artifacts
- `data/logs` runtime JSONL logs
- `data/cache` search/page/embedding caches

### Bootstrap + Training Commands

From `backend/`:

1. `python training/bootstrap_datasets.py`
2. `python training/train_consistency_model.py`
3. `python training/train_calibrator.py` (requires labeled logs with `human_label`)
4. `python training/tune_consistency_model.py`

### Research-Guided Tuning Notes

The tuning workflow in `backend/training/tune_consistency_model.py` is guided by:

- FEVER dataset framing and evidence-conditioned claim verification
- FactCC weak-supervision consistency learning
- Sparse lexical features + calibrated linear models as fast first-line classifiers

## Development Notes

- For account/history features, login from UI first.
- Streaming route emits progressive events; frontend handles cancellation and stream-end states.
- Chat endpoint stores conversation even if model API is rate-limited (fallback assistant reply is returned).

## Testing

From `backend/`:

```bash
pytest -n auto
```

Deterministic validation suite (engineering + medical + safety):

```bash
pytest -q tests/test_deterministic_validation.py
```

This suite enforces advanced deployment assertions:

- technical claim without direct evidence cannot be verified
- safety-critical low-confidence claims are downgraded to uncertain
- strong high-trust contradiction forces hallucination
- low-reliability-only support cannot produce verified

Covered groups include:

- engineering fundamentals and falsehoods
- complex engineering claims
- medical fundamentals and falsehoods
- medical ambiguity
- adversarial/bias-heavy research cases
- numeric consistency (unit-equivalent constants)
- logic/constraint consistency checks

Strict pass expectation for production readiness:

1. engineering truths pass
2. engineering falsehoods fail
3. medical truths pass with guardrails
4. medical falsehoods fail
5. ambiguous claims are not verified
6. safety-critical uncertain downgrade works

Blind benchmark + iterative tuner (100 unique statements per category):

```bash
python -m tools.benchmark_harness generate --per-field-per-category 100 --holdout-ratio 0.2 --seed 23 --force
python -m tools.benchmark_harness evaluate --split holdout
python -m tools.benchmark_harness autotune --iterations 10
```

Properties of this harness:

- builds a field-balanced controlled benchmark with **100 statements per field per category**
  - current default: 22 fields × 3 categories × 100 = 6600 cases
- train/holdout split per category (blind aggregate reporting)
- balanced multi-domain coverage across 20+ fields with multiple statements per field:
  - astronomy, physics, chemistry, biology, medicine
  - history, geography, economics, finance, law
  - sports, computer science, software engineering, mathematics
  - literature, art, music, linguistics, food/nutrition, beauty/cosmetics
- logs only category metrics + failure types (`RETRIEVAL_FAILURE`, `RELATION_FAILURE`, `NUMERIC_FAILURE`, `STANCE_FAILURE`, `OVER_STRICT`, `OVER_SOFT`)
- penalizes uncertainty on absolute (`true`/`false`) items using low-confidence penalty in report scoring
- writes tuning profile to `data/models/deterministic_tuning_profile.json`
- app/runtime tuning knobs are read from `DET_*` environment variables in the deterministic voter

Recent blind cycle result on holdout:

- overall accuracy: `0.8902`
- uncertainty-adjusted overall: `0.8297`
- macro accuracy: `0.8902`
- category accuracy: `true=0.7`, `false=0.9705`, `probable=1.0`

From `frontend/`:

```bash
npm run build
```

## Troubleshooting

- **401 on protected endpoints:** token missing/expired. Login again.
- **Chat returns fallback reply:** LLM provider unavailable or rate limited.
- **Slow runs/timeouts:** lower concurrency and tighten retrieval limits in `.env`.
- **Port busy:** startup scripts auto-select fallback backend port.

