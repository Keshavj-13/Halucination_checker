# Hallucination Audit System

A minimal, clean starter project for auditing documents for hallucinations.

## Project Structure

- `backend/`: FastAPI server
  - `main.py`: Entry point
  - `routes/audit.py`: API endpoints
  - `services/`: Claim extraction and verification logic
  - `models/schemas.py`: Pydantic data models
- `frontend/`: React + Vite + Tailwind CSS dashboard
  - `src/App.jsx`: Main UI
  - `src/api.js`: Backend communication with fallback logic
  - `src/components/`: Reusable UI components

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

- **Claim Extraction**: Automatically splits input text into individual sentences.
- **Heuristic Verification**: Uses simple rules (numbers, trigger words) to simulate verification.
- **Interactive Dashboard**: View summary stats and detailed evidence for each claim.
- **Fallback Logic**: Frontend gracefully falls back to sample data if the backend is offline.
