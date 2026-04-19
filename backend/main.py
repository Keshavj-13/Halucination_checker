from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from routes.audit import router
from services.embedding_service import embedding_service
from services.retrieval_pipeline import retrieval_pipeline
from services.verifier import shutdown_verifier_executors
from services.telemetry import telemetry
import time
import os

import logging

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

app.include_router(router)


@app.get("/")
def root():
    return {"message": "Hallucination Audit API is running. Use /audit or /audit/stream."}


@app.get("/health")
def health():
    return {"status": "ok"}
