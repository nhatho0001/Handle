import base64
import io
import logging
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import easyocr

import fitz  # PyMuPDF
import docx
import openpyxl

app = FastAPI(title="Copilot Studio - File to Text API")

# Khởi tạo reader một lần khi server start (tránh load model lại mỗi request)
ocr_reader = easyocr.Reader(["vi", "en"], gpu=False)


class FileInput(BaseModel):
    fileName: str
    contentBytes: str  # base64 encoded


class FileOutput(BaseModel):
    fileName: str
    fileType: str
    text: str


def get_extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower().lstrip(".")


def extract_from_pdf(file_bytes: bytes) -> str:
    text_parts = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            page_text = page.get_text()
            if page_text.strip():
                text_parts.append(page_text)
            else:
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                results = ocr_reader.readtext(img_bytes, detail=0)
                text_parts.append("\n".join(results))
    return "\n".join(text_parts).strip()


def extract_from_docx(file_bytes: bytes) -> str:
    f = io.BytesIO(file_bytes)
    document = docx.Document(f)

    parts = []

    for para in document.paragraphs:
        if para.text.strip():
            parts.append(para.text)

    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))

    return "\n".join(parts).strip()


def extract_from_xlsx(file_bytes: bytes) -> str:
    f = io.BytesIO(file_bytes)
    wb = openpyxl.load_workbook(f, data_only=True)

    parts = []
    for sheet in wb.worksheets:
        parts.append(f"=== Sheet: {sheet.title} ===")
        for row in sheet.iter_rows(values_only=True):
            if row is None:
                continue
            row_values = [str(cell) if cell is not None else "" for cell in row]
            if any(v.strip() for v in row_values):
                parts.append("\t".join(row_values))

    return "\n".join(parts).strip()


def extract_from_image(file_bytes: bytes) -> str:
    results = ocr_reader.readtext(file_bytes, detail=0)
    return "\n".join(results).strip()


EXTENSION_MAP = {
    "pdf": ("pdf", extract_from_pdf),
    "doc": ("word", extract_from_docx),
    "docx": ("word", extract_from_docx),
    "xls": ("excel", extract_from_xlsx),
    "xlsx": ("excel", extract_from_xlsx),
    "png": ("image", extract_from_image),
    "jpg": ("image", extract_from_image),
    "jpeg": ("image", extract_from_image),
    "bmp": ("image", extract_from_image),
    "tiff": ("image", extract_from_image),
    "gif": ("image", extract_from_image),
}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/extract", response_model=FileOutput)
def extract_text(payload: FileInput):
    ext = get_extension(payload.fileName)

    if ext not in EXTENSION_MAP:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    file_type, extractor = EXTENSION_MAP[ext]

    try:
        file_bytes = base64.b64decode(payload.contentBytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 in contentBytes")

    try:
        text = extractor(file_bytes)
    except Exception as e:
        logger.exception("Extraction failed for file=%s ext=%s", payload.fileName, ext)
        raise HTTPException(status_code=500, detail=f"Failed to extract content: {str(e)}")

    return FileOutput(fileName=payload.fileName, fileType=file_type, text=text)
