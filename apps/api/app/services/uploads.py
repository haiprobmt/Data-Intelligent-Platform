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

DOCUMENT_FILE_EXTENSIONS = {".doc", ".docx", ".xlsx", ".xls", ".csv", ".txt", ".md", ".pdf"}
SOURCE_MIME_PREFIXES = {"text/", "application/json", "application/vnd", "application/octet-stream"}
DOCUMENT_MIME_PREFIXES = {"text/", "application/pdf", "application/vnd", "application/msword", "application/octet-stream"}


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
        validate_mime_type(file.content_type, DOCUMENT_MIME_PREFIXES)
    if category == "sources":
        validate_mime_type(file.content_type, SOURCE_MIME_PREFIXES)
    upload_root = Path(get_settings().upload_dir) / category / tenant_id
    upload_root.mkdir(parents=True, exist_ok=True)
    stored_path = upload_root / f"{uuid4()}_{file_name}"
    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    total_bytes = 0
    with stored_path.open("wb") as handle:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                handle.close()
                stored_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"Uploaded file exceeds {get_settings().max_upload_size_mb} MB")
            handle.write(chunk)
    if total_bytes == 0:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    scan_file_for_viruses(stored_path)
    return stored_path


def validate_mime_type(content_type: str | None, allowed_prefixes: set[str]) -> None:
    if not content_type:
        return
    if not any(content_type.startswith(prefix) for prefix in allowed_prefixes):
        raise HTTPException(status_code=400, detail=f"Unsupported MIME type: {content_type}")


def scan_file_for_viruses(file_path: Path) -> None:
    return None


def _safe_file_name(file_name: str) -> str:
    name = Path(file_name).name.strip() or "upload"
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)
