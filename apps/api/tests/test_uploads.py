import pytest
from fastapi import HTTPException

from app.services.uploads import validate_document_file, validate_mime_type, validate_source_file


def test_source_upload_extension_must_match_system_type():
    with pytest.raises(HTTPException) as exc_info:
        validate_source_file("excel", "customers.csv")

    assert exc_info.value.status_code == 400
    assert ".xlsx" in exc_info.value.detail


def test_pdf_is_allowed_for_documents():
    validate_document_file("requirements.pdf")


def test_mime_type_rejects_unexpected_binary():
    with pytest.raises(HTTPException) as exc_info:
        validate_mime_type("image/png", {"application/pdf"})

    assert exc_info.value.status_code == 400
