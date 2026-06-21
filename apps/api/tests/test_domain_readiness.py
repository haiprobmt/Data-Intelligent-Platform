from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import test_source_system_connection as call_source_system_connection
from app.models import DataQualityIssue, Document, SourceSystem
from app.security import AuthContext
from app.services.documents import extract_document
from app.services.entity_discovery import detect_entity
from app.services.profiler import run_profile
from app.services.scanner import run_metadata_scan


def test_entity_detection_handles_multiple_domains_and_generic_names():
    assert detect_entity("gl_journal_entries", ["entry_id", "cost_center", "amount"]) == "Journal Entry"
    assert detect_entity("patient_claims", ["claim_id", "member_id", "diagnosis_code"]) == "Claim"
    assert detect_entity("raw_inventory_movements_upload", ["sku", "warehouse_id", "quantity"]) == "Inventory Item"
    assert detect_entity("partner_onboarding_records", ["partner_name", "owner_email"]) == "Partner Onboarding"


def test_document_extraction_uses_local_label_value_fallback_when_bedrock_is_unavailable(tmp_path, monkeypatch):
    document_path = tmp_path / "business-case.txt"
    document_path.write_text(
        "Entity Name: Contoso Retail\n"
        "Reporting Period: FY2026 Q1\n"
        "Risk Score: 82\n",
        encoding="utf-8",
    )
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr("app.services.documents._extract_with_bedrock", lambda *args, **kwargs: None)
    try:
        document = Document(
            tenant_id="tenant-docs",
            file_name="business-case.txt",
            file_path=str(document_path),
            document_type="Business case",
            target_schema={"columns": ["entity_name", "reporting_period", "risk_score", "owner"]},
        )
        db.add(document)
        db.commit()

        result = extract_document(db, "tenant-docs", document.id)

        assert result["fields"] == {
            "entity_name": "Contoso Retail",
            "reporting_period": "FY2026 Q1",
            "risk_score": "82",
            "owner": "Requires review",
        }
        assert result["confidence_score"] == 0.75
    finally:
        db.close()


def test_profile_creates_duplicate_row_issue_for_sql_sources(tmp_path):
    source_database = tmp_path / "source.db"
    source_engine = create_engine(f"sqlite:///{source_database}")
    with source_engine.begin() as connection:
        connection.execute(text("create table records (business_key text, category text, amount integer)"))
        connection.execute(
            text("insert into records values (:business_key, :category, :amount)"),
            [
                {"business_key": "A-1", "category": "x", "amount": 100},
                {"business_key": "A-1", "category": "x", "amount": 100},
                {"business_key": "B-2", "category": "y", "amount": 200},
            ],
        )

    app_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=app_engine)
    db = sessionmaker(bind=app_engine)()
    try:
        source = SourceSystem(
            tenant_id="tenant-profile",
            name="Generic source",
            system_type="sqlite",
            secret_reference=f"sqlite:///{source_database}",
        )
        db.add(source)
        db.commit()

        run_metadata_scan(db, "tenant-profile", source.id, scan_mode="full_profile")
        run_profile(db, "tenant-profile", source.id)

        issue_types = db.scalars(select(DataQualityIssue.issue_type).where(DataQualityIssue.tenant_id == "tenant-profile")).all()
        assert "Duplicate rows detected" in issue_types
    finally:
        db.close()


def test_source_system_connection_endpoint_updates_status(tmp_path):
    source_file = tmp_path / "source.csv"
    source_file.write_text("id,name\n1,Ada\n", encoding="utf-8")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        source = SourceSystem(
            tenant_id="tenant-connect",
            name="Uploaded source",
            system_type="csv",
            secret_reference=f"file://{source_file}",
        )
        db.add(source)
        db.commit()

        result = call_source_system_connection(
            source.id,
            AuthContext(user_id="user-1", email="analyst@example.com", tenant_id="tenant-connect", role="analyst"),
            db,
        )

        assert result == {"status": "connected", "source_system_id": source.id}
        assert db.get(SourceSystem, source.id).status == "connected"
    finally:
        db.close()


def test_source_system_connection_endpoint_rejects_other_tenant(tmp_path):
    source_file = tmp_path / "source.csv"
    source_file.write_text("id,name\n1,Ada\n", encoding="utf-8")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        source = SourceSystem(
            tenant_id="tenant-a",
            name="Uploaded source",
            system_type="csv",
            secret_reference=f"file://{source_file}",
        )
        db.add(source)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            call_source_system_connection(
                source.id,
                AuthContext(user_id="user-1", email="analyst@example.com", tenant_id="tenant-b", role="analyst"),
                db,
            )

        assert exc_info.value.status_code == 404
    finally:
        db.close()