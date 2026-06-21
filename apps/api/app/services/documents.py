from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Document
from app.services.audit import audit
from app.services.bedrock import invoke_bedrock_json


def extract_document(db: Session, tenant_id: str, document_id: str) -> dict:
    document = db.get(Document, document_id)
    if document is None or document.tenant_id != tenant_id:
        raise ValueError("Document not found for tenant")

    columns = (document.target_schema or {}).get("columns", [])
    bedrock_result = _extract_with_bedrock(document.file_name, document.document_type, columns)
    extracted = bedrock_result.get("fields") if bedrock_result else None
    confidence = bedrock_result.get("confidence_score") if bedrock_result else None
    document.extracted_fields = extracted if isinstance(extracted, dict) else {column: "Requires Bedrock review" for column in columns}
    document.confidence_score = float(confidence) if isinstance(confidence, (int, float)) else 0.0
    document.status = "needs_review"
    audit(db, tenant_id, "document.extract", {"document_id": document.id, "confidence": document.confidence_score})
    db.commit()
    return {"document_id": document.id, "confidence_score": document.confidence_score, "fields": extracted}


def approve_document(db: Session, tenant_id: str, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.tenant_id != tenant_id:
        raise ValueError("Document not found for tenant")
    if not document.extracted_fields:
        raise ValueError("Document must be extracted before approval")
    document.status = "approved"
    document.approved_at = datetime.utcnow()
    audit(db, tenant_id, "document.approve", {"document_id": document.id})
    db.commit()
    db.refresh(document)
    return document


def _extract_with_bedrock(file_name: str, document_type: str, columns: list[str]) -> dict | None:
    prompt = f"""
You are extracting structured data for an enterprise data assessment portal.
The uploaded file is named {file_name!r} and was classified as {document_type!r}.
Return strict JSON only with this shape:
{{"confidence_score": 0.0, "fields": {{"column_name": "value"}}}}
Only include the requested fields: {columns}.
If the file contents are not available in the prompt, set unknown values to "Requires review" and confidence_score to 0.
""".strip()
    return invoke_bedrock_json(prompt, max_tokens=900)
