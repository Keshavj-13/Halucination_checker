import logging

from fastapi import APIRouter, File, UploadFile

from models.schemas import TextExtractionResponse
from services.readable_text import extract_readable_text

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger("audit-api.documents")


@router.post("/readable-text", response_model=TextExtractionResponse)
def extract_document_text(file: UploadFile = File(...)):
    result = extract_readable_text(file)
    logger.info(
        "Extracted %s readable characters from %s",
        result.characters,
        result.filename,
    )
    return TextExtractionResponse(
        filename=result.filename,
        content_type=result.content_type,
        characters=result.characters,
        text=result.text,
    )
