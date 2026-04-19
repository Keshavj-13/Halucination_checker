import io
import importlib
import logging
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile

logger = logging.getLogger("audit-api.readable-text")

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml", ".log"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx", ".pptx"}


@dataclass(frozen=True)
class ReadableTextResult:
    filename: str
    content_type: str | None
    text: str

    @property
    def characters(self) -> int:
        return len(self.text)


def _file_extension(filename: str) -> str:
    lower = filename.lower()
    dot_index = lower.rfind(".")
    if dot_index == -1:
        return ""
    return lower[dot_index:]


def _decode_text(content: bytes, filename: str) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue

    logger.warning("Unable to decode text file %s with supported encodings", filename)
    raise HTTPException(status_code=400, detail="Unsupported text encoding.")


def _extract_pdf(content: bytes) -> str:
    try:
        PdfReader = importlib.import_module("PyPDF2").PdfReader
    except Exception as exc:
        raise HTTPException(status_code=500, detail="PDF support missing. Install PyPDF2.") from exc

    pdf_reader = PdfReader(io.BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in pdf_reader.pages)


def _extract_docx(content: bytes) -> str:
    try:
        Document = importlib.import_module("docx").Document
    except Exception as exc:
        raise HTTPException(status_code=500, detail="DOCX support missing. Install python-docx.") from exc

    document = Document(io.BytesIO(content))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _extract_pptx(content: bytes) -> str:
    try:
        Presentation = importlib.import_module("pptx").Presentation
    except Exception as exc:
        raise HTTPException(status_code=500, detail="PPTX support missing. Install python-pptx.") from exc

    presentation = Presentation(io.BytesIO(content))
    slide_text: list[str] = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                slide_text.append(shape.text)
    return "\n".join(slide_text)


def extract_readable_text(file: UploadFile) -> ReadableTextResult:
    filename = file.filename or "uploaded-file"
    extension = _file_extension(filename)

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload PDF, DOCX, PPTX, TXT, Markdown, CSV, JSON, HTML, XML, or LOG.",
        )

    try:
        content = file.file.read()
        logger.info("Extracting readable text from %s (%s bytes)", filename, len(content))

        if extension == ".pdf":
            text = _extract_pdf(content)
        elif extension == ".docx":
            text = _extract_docx(content)
        elif extension == ".pptx":
            text = _extract_pptx(content)
        else:
            text = _decode_text(content, filename)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to extract readable text from %s", filename)
        raise HTTPException(status_code=500, detail="Failed to extract readable text from uploaded file.") from exc

    if not text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in the uploaded file.")

    return ReadableTextResult(
        filename=filename,
        content_type=file.content_type,
        text=text,
    )
