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


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(180))
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(40), default="viewer")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AssessmentProject(Base):
    __tablename__ = "assessment_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120))
    primary_goal: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AssessmentProfile(Base):
    __tablename__ = "assessment_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("assessment_projects.id"), index=True)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    fabric_score: Mapped[int] = mapped_column(Integer, default=0)
    databricks_score: Mapped[int] = mapped_column(Integer, default=0)
    recommended_platform: Mapped[str] = mapped_column(String(80), default="Microsoft Fabric")
    reasoning: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConnectionSecret(Base):
    __tablename__ = "connection_secrets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    reference: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SourceSystem(Base):
    __tablename__ = "source_systems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    system_type: Mapped[str] = mapped_column(String(80), nullable=False)
    connection_type: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), default="registered")
    secret_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("connection_secrets.id"), index=True)
    secret_reference: Mapped[str | None] = mapped_column(String(500))
    scan_mode: Mapped[str] = mapped_column(String(40), default="metadata_only")
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
    row_count_is_estimated: Mapped[bool] = mapped_column(Boolean, default=True)
    detected_entity: Mapped[str | None] = mapped_column(String(120))
    owner: Mapped[str | None] = mapped_column(String(180))
    steward: Mapped[str | None] = mapped_column(String(180))
    source_freshness_at: Mapped[datetime | None] = mapped_column(DateTime)
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


class MetadataIndex(Base):
    __tablename__ = "metadata_indexes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    table_id: Mapped[str] = mapped_column(String(36), ForeignKey("metadata_tables.id"), index=True, nullable=False)
    index_name: Mapped[str] = mapped_column(String(180), nullable=False)
    column_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_unique: Mapped[bool] = mapped_column(Boolean, default=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MetadataRelationship(Base):
    __tablename__ = "metadata_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    source_system_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_systems.id"), index=True, nullable=False)
    from_table_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("metadata_tables.id"), index=True)
    from_table: Mapped[str] = mapped_column(String(180), nullable=False)
    from_schema: Mapped[str | None] = mapped_column(String(120))
    from_columns: Mapped[list[str]] = mapped_column(JSON, default=list)
    to_table_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("metadata_tables.id"), index=True)
    to_table: Mapped[str] = mapped_column(String(180), nullable=False)
    to_schema: Mapped[str | None] = mapped_column(String(120))
    to_columns: Mapped[list[str]] = mapped_column(JSON, default=list)
    relationship_type: Mapped[str] = mapped_column(String(80), default="FOREIGN_KEY")
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MetadataView(Base):
    __tablename__ = "metadata_views"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    source_system_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_systems.id"), index=True, nullable=False)
    database_name: Mapped[str | None] = mapped_column(String(120))
    schema_name: Mapped[str | None] = mapped_column(String(120))
    view_name: Mapped[str] = mapped_column(String(180), nullable=False)
    definition: Mapped[str | None] = mapped_column(Text)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MetadataProcedure(Base):
    __tablename__ = "metadata_procedures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    source_system_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_systems.id"), index=True, nullable=False)
    schema_name: Mapped[str | None] = mapped_column(String(120))
    procedure_name: Mapped[str] = mapped_column(String(180), nullable=False)
    definition: Mapped[str | None] = mapped_column(Text)
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
    file_path: Mapped[str | None] = mapped_column(String(500))
    document_type: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="uploaded")
    target_schema: Mapped[dict | None] = mapped_column(JSON)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extracted_fields: Mapped[dict | None] = mapped_column(JSON)
    extraction_metadata: Mapped[dict | None] = mapped_column(JSON)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentExtractedField(Base):
    __tablename__ = "document_extracted_fields"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True, nullable=False)
    field_name: Mapped[str] = mapped_column(String(180), nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    reference: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    reviewed_value: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(40), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSON)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), index=True, nullable=False)
    level: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    actor: Mapped[str] = mapped_column(String(180), default="portal-user")
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LlmUsageLog(Base):
    __tablename__ = "llm_usage_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(180), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    purpose: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
