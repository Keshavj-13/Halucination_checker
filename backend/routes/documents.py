import logging

from fastapi import APIRouter, Depends, File, UploadFile

from backend.models.schemas import TextExtractionResponse
from backend.services.auth_store import AuthenticatedUser, get_current_user
from backend.services.readable_text import extract_readable_text

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger("audit-api.documents")


@router.post("/readable-text", response_model=TextExtractionResponse)
def extract_document_text(
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    result = extract_readable_text(file)
    logger.info(
        "Extracted %s readable characters from %s for user '%s'",
        result.characters,
        result.filename,
        current_user.username,
    )
    return TextExtractionResponse(
        filename=result.filename,
        content_type=result.content_type,
        characters=result.characters,
        text=result.text,
    )
