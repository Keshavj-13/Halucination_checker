from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.audit import router

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("audit-api")

app = FastAPI(title="Hallucination Audit API")

@app.on_event("startup")
async def startup_event():
    logger.info("API is starting up...")

# Allow all origins for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
