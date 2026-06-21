from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentExtractedField
from app.services.audit import audit
from app.services.bedrock import invoke_bedrock_json
from app.services.document_text import extract_text_from_file


def extract_document(db: Session, tenant_id: str, document_id: str) -> dict:
    document = db.get(Document, document_id)
    if document is None or document.tenant_id != tenant_id:
        raise ValueError("Document not found for tenant")

    columns = (document.target_schema or {}).get("columns", [])
    extracted_text, extraction_metadata = extract_text_from_file(document.file_path)
    document.extracted_text = extracted_text
    document.extraction_metadata = extraction_metadata
    bedrock_result = _extract_with_bedrock(db, tenant_id, document.file_name, document.document_type, columns, extracted_text)
    extracted = bedrock_result.get("fields") if bedrock_result else None
    confidence = bedrock_result.get("confidence_score") if bedrock_result else None
    field_confidence = bedrock_result.get("field_confidence") if bedrock_result else {}
    references = bedrock_result.get("references") if bedrock_result else {}
    document.extracted_fields = extracted if isinstance(extracted, dict) else {column: "Requires Bedrock review" for column in columns}
    document.confidence_score = float(confidence) if isinstance(confidence, (int, float)) else 0.0
    document.status = "needs_review"
    db.execute(delete(DocumentExtractedField).where(DocumentExtractedField.tenant_id == tenant_id, DocumentExtractedField.document_id == document.id))
    for column, value in document.extracted_fields.items():
        confidence_value = field_confidence.get(column) if isinstance(field_confidence, dict) else None
        reference = references.get(column) if isinstance(references, dict) else None
        db.add(
            DocumentExtractedField(
                tenant_id=tenant_id,
                document_id=document.id,
                field_name=column,
                value=str(value) if value is not None else None,
                confidence=float(confidence_value) if isinstance(confidence_value, (int, float)) else None,
                reference=str(reference) if reference is not None else None,
                page_number=_page_number_from_reference(str(reference)) if reference is not None else None,
            )
        )
    audit(
        db,
        tenant_id,
        "document.extract",
        {"document_id": document.id, "confidence": document.confidence_score, "text_characters": len(extracted_text)},
    )
    db.commit()
    return {
        "document_id": document.id,
        "confidence_score": document.confidence_score,
        "fields": document.extracted_fields,
        "text_characters": len(extracted_text),
        "extraction_metadata": extraction_metadata,
    }


def approve_document(db: Session, tenant_id: str, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.tenant_id != tenant_id:
        raise ValueError("Document not found for tenant")
    if not document.extracted_fields:
        raise ValueError("Document must be extracted before approval")
    reviewed_fields = db.scalars(select(DocumentExtractedField).where(DocumentExtractedField.tenant_id == tenant_id, DocumentExtractedField.document_id == document.id)).all()
    if reviewed_fields:
        document.extracted_fields = {
            field.field_name: field.reviewed_value if field.reviewed_value is not None else field.value
            for field in reviewed_fields
        }
    document.status = "approved"
    document.approved_at = datetime.utcnow()
    audit(db, tenant_id, "document.approve", {"document_id": document.id})
    db.commit()
    db.refresh(document)
    return document


def _extract_with_bedrock(db: Session, tenant_id: str, file_name: str, document_type: str, columns: list[str], extracted_text: str) -> dict | None:
    text_for_prompt = extracted_text[:18000]
    prompt = f"""
You are extracting structured data for an enterprise data assessment portal.
The uploaded file is named {file_name!r} and was classified as {document_type!r}.
Return strict JSON only with this shape:
{{"confidence_score": 0.0, "fields": {{"column_name": "value"}}, "field_confidence": {{"column_name": 0.0}}, "references": {{"column_name": "page or text evidence"}}}}
Only include the requested fields: {columns}.
Use this extracted document text:
{text_for_prompt}

If the text is empty or a requested value is not present, set the field to "Requires review" and lower the confidence score.
""".strip()
    return invoke_bedrock_json(prompt, max_tokens=900, db=db, tenant_id=tenant_id, purpose="document_extraction")


def _page_number_from_reference(reference: str) -> int | None:
    lower = reference.lower()
    if "page" not in lower:
        return None
    parts = lower.replace(":", " ").replace("-", " ").split()
    for index, part in enumerate(parts):
        if part == "page" and index + 1 < len(parts):
            try:
                return int(parts[index + 1])
            except ValueError:
                return None
    return None
