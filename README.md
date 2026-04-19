# Hallucination Audit System

A minimal, clean starter project for auditing documents for hallucinations.

## Project Structure
...
## LLM Configuration

This system uses LLMs for atomic claim extraction and verification. It supports **Ollama** (local) and **OpenAI** (API).

1. Copy the example env file:
   ```bash
   cp backend/.env.example backend/.env
   ```
2. Edit `backend/.env` to choose your provider and set your API key if using OpenAI.
3. If using Ollama, ensure it is running (`ollama serve`) and you have the model pulled (`ollama pull llama3`).

## Setup and Run

### The Quick Way (Single Command)

If you have both Python and Node.js installed, you can start both services with:
```bash
./start.sh
```

### The Manual Way

#### Backend
1. Navigate to the backend directory: `cd backend`
2. Install dependencies: `pip install -r requirements.txt`
3. Run the server: `uvicorn main:app --reload`

#### Frontend
1. Navigate to the frontend directory: `cd frontend`
2. Install dependencies: `npm install`
3. Run the development server: `npm run dev`

## Features

- **Atomic claim extraction**: Splits sentences into minimal factual units with start/end character offsets.
- **Async retrieval + multicore CPU pipeline**: Concurrent search/scraping plus process-pool chunking.
- **Multi-factor source reliability**: Domain prior, content quality, freshness, cross-source support, spam penalties.
- **Five-voter ensemble**: Heuristic, semantic, entity, consistency model, and weak LLM voter.
- **Calibrated consensus**: Data-calibrated fusion over voter outputs + reliability + clustering signal.
- **Explainable UI**: Highlighted claims, per-voter scores, source reliability, evidence links, contradictions.
- **Structured retraining logs**: Per-claim JSONL logs with intermediate outputs.

## Cumulative Multilayer Ensemble Auditor

The backend now runs a modular multilayer stack with deterministic logging and calibration hooks:

1. **Atomic claim decomposition** with character offsets
2. **Async retrieval pipeline** (DuckDuckGo, concurrent scraping, chunking)
3. **Multi-factor source reliability** (domain, quality, freshness, cross-source support, spam penalty)
4. **Evidence clustering signal** (auxiliary support confidence from independent clusters)
4. **Ensemble voters**
   - Heuristic TF-IDF voter
   - Semantic embedding voter
   - Entity/date/number voter
   - Lightweight consistency model voter
   - Weak LLM voter
5. **Calibrated consensus engine** (meta-classifier if available)
6. **Per-claim pipeline deadline guard** (default 8s, configurable)
7. **JSONL logging** for every claim in `data/logs/audit_claim_logs.jsonl`

### Data layout

- `data/raw` downloaded datasets
- `data/processed` cleaned training/eval rows
- `data/models` trained classifier and calibrator artifacts
- `data/logs` runtime JSONL logs
- `data/cache` search/page/embedding caches

### Bootstrap + training commands

From `backend/`:

1. `python training/bootstrap_datasets.py`
2. `python training/train_consistency_model.py`
3. `python training/train_calibrator.py` (requires labeled logs with `human_label`)
4. `python training/tune_consistency_model.py` (randomized hyperparameter search for lightweight models)

### Research-guided tuning notes

The tuning workflow in [backend/training/tune_consistency_model.py](backend/training/tune_consistency_model.py) is guided by:

- FEVER dataset framing and evidence-conditioned claim verification.
- FactCC weak-supervision consistency learning for scalable factuality checks.
- Sparse lexical features + calibrated linear models as fast first-line classifiers before heavier architectures.

### Runtime knobs (backend/.env)

- `MAX_SEARCH_RESULTS`
- `MAX_EVIDENCE_CHUNKS`
- `SCRAPE_CONCURRENCY`
- `RETRIEVAL_DEADLINE_SECONDS`
- `MAX_PAGES_TO_PROCESS`
- `CLAIM_PIPELINE_DEADLINE_SECONDS`

### Tests

From `backend/`:

- `pytest -n auto`
