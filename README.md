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

#### Linux/macOS
```bash
./start.sh
```

#### Windows
```cmd
start.cmd
```

### The Manual Way

#### Backend
1. Navigate to the backend directory: `cd backend`
2. Install dependencies: `py -m pip install -r requirements.txt`
3. Run the server: `py -m uvicorn main:app --reload`

#### Frontend
1. Navigate to the frontend directory: `cd frontend`
2. Install dependencies:
   - In PowerShell: `npm.cmd install`
   - Or: `cmd /c "npm install"`
3. Run the development server:
   - In PowerShell: `npm.cmd run dev`
   - Or: `cmd /c "npm run dev"`

If PowerShell blocks `npm`, use `npm.cmd` or `cmd /c`.

## Features

- **Claim Extraction**: Automatically splits input text into individual sentences.
- **Heuristic Verification**: Uses simple rules (numbers, trigger words) to simulate verification.
- **Interactive Dashboard**: View summary stats and detailed evidence for each claim.
- **Fallback Logic**: Frontend gracefully falls back to sample data if the backend is offline.
