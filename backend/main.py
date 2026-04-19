import os
import sys
import time
from pathlib import Path

import logging

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"

for import_path in (ROOT_DIR, BACKEND_DIR):
    path_text = str(import_path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from routes.audit import router as audit_router
from services.embedding_service import embedding_service
from services.retrieval_pipeline import retrieval_pipeline
from services.verifier import shutdown_verifier_executors
from services.telemetry import telemetry

from backend.routes.auth import router as auth_router
from backend.routes.chat import router as chat_router
from backend.routes.documents import router as documents_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("audit-api")

app = FastAPI(title="Hallucination Audit API")


@app.middleware("http")
async def request_trace_middleware(request: Request, call_next):
    started = time.perf_counter()
    telemetry.event("http_request_start", stage="http", message=f"{request.method} {request.url.path}")
    response = await call_next(request)
    telemetry.event(
        "http_request_done",
        stage="http",
        message=f"{request.method} {request.url.path} -> {response.status_code}",
        payload={"runtime_ms": round((time.perf_counter() - started) * 1000.0, 2)},
    )
    return response

@app.on_event("startup")
async def startup_event():
    logger.info("API is starting up...")
    telemetry.event(
        "service_start",
        stage="service",
        message="backend startup",
        payload={"pid": os.getpid(), "ts": time.time()},
    )

@app.on_event("shutdown")
async def shutdown_event():
    telemetry.event("service_stop", stage="service", message="backend shutdown", payload={"pid": os.getpid(), "ts": time.time()})
    shutdown_verifier_executors()
    await embedding_service.aclose()
    await retrieval_pipeline.aclose()

# Allow all origins for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(audit_router)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(documents_router)

if FRONTEND_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS_DIR), name="frontend-assets")


@app.get("/")
def root():
    if FRONTEND_DIST_DIR.exists():
        return FileResponse(FRONTEND_DIST_DIR / "index.html")

    return {"message": "Hallucination Audit API is running. Use /audit or /audit/stream."}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_app(full_path: str):
    if not FRONTEND_DIST_DIR.exists():
        return {"message": "Frontend build not found. Run the startup script or build the frontend first."}

    candidate = FRONTEND_DIST_DIR / full_path
    if candidate.is_file():
        return FileResponse(candidate)

    return FileResponse(FRONTEND_DIST_DIR / "index.html")
