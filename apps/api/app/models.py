from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid4())


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SourceSystem(Base):
    __tablename__ = "source_systems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    system_type: Mapped[str] = mapped_column(String(80), nullable=False)
    connection_type: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), default="registered")
    secret_reference: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tables: Mapped[list["MetadataTable"]] = relationship(cascade="all, delete-orphan")


class MetadataTable(Base):
    __tablename__ = "metadata_tables"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    source_system_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_systems.id"), index=True, nullable=False)
    database_name: Mapped[str | None] = mapped_column(String(120))
    schema_name: Mapped[str | None] = mapped_column(String(120))
    table_name: Mapped[str] = mapped_column(String(180), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    detected_entity: Mapped[str | None] = mapped_column(String(120))
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    columns: Mapped[list["MetadataColumn"]] = relationship(cascade="all, delete-orphan")


class MetadataColumn(Base):
    __tablename__ = "metadata_columns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    table_id: Mapped[str] = mapped_column(String(36), ForeignKey("metadata_tables.id"), index=True, nullable=False)
    column_name: Mapped[str] = mapped_column(String(180), nullable=False)
    data_type: Mapped[str | None] = mapped_column(String(120))
    is_nullable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_primary_key: Mapped[bool] = mapped_column(Boolean, default=False)
    is_foreign_key: Mapped[bool] = mapped_column(Boolean, default=False)
    null_percentage: Mapped[float | None] = mapped_column(Float)
    distinct_count: Mapped[int | None] = mapped_column(Integer)
    sample_values: Mapped[list[str] | None] = mapped_column(JSON)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    table_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("metadata_tables.id"), index=True)
    column_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("metadata_columns.id"), index=True)
    issue_type: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(40), nullable=False)
    estimated_effort: Mapped[str] = mapped_column(String(80), nullable=False)
    business_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PocAsset(Base):
    __tablename__ = "poc_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(80), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(120), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(250), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(250), nullable=False)
    document_type: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="uploaded")
    target_schema: Mapped[dict | None] = mapped_column(JSON)
    extracted_fields: Mapped[dict | None] = mapped_column(JSON)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    actor: Mapped[str] = mapped_column(String(180), default="portal-user")
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
