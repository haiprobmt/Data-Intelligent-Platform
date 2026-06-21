import re
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.config import get_settings

SOURCE_FILE_EXTENSIONS: dict[str, set[str]] = {
    "csv": {".csv"},
    "excel": {".xlsx", ".xls"},
    "json": {".json"},
    "parquet": {".parquet"},
}

DOCUMENT_FILE_EXTENSIONS = {".doc", ".docx", ".xlsx", ".xls", ".csv", ".txt", ".md"}


def validate_source_file(system_type: str, file_name: str) -> None:
    extension = Path(file_name).suffix.lower()
    allowed = SOURCE_FILE_EXTENSIONS.get(system_type.lower())
    if not allowed:
        raise HTTPException(status_code=400, detail=f"File upload is not supported for {system_type}")
    if extension not in allowed:
        allowed_list = ", ".join(sorted(allowed))
        raise HTTPException(status_code=400, detail=f"{system_type} sources must use {allowed_list} files")


def validate_document_file(file_name: str) -> None:
    extension = Path(file_name).suffix.lower()
    if extension not in DOCUMENT_FILE_EXTENSIONS:
        allowed_list = ", ".join(sorted(DOCUMENT_FILE_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Upload documents must use one of: {allowed_list}")


async def save_uploaded_file(file: UploadFile, tenant_id: str, category: str) -> Path:
    file_name = _safe_file_name(file.filename or "upload")
    if category == "documents":
        validate_document_file(file_name)
    upload_root = Path(get_settings().upload_dir) / category / tenant_id
    upload_root.mkdir(parents=True, exist_ok=True)
    stored_path = upload_root / f"{uuid4()}_{file_name}"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    stored_path.write_bytes(content)
    return stored_path


def _safe_file_name(file_name: str) -> str:
    name = Path(file_name).name.strip() or "upload"
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)
