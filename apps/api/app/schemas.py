from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceSystemCreate(BaseModel):
    name: str
    system_type: str
    connection_type: str = "metadata-only"
    secret_reference: str | None = Field(
        default=None,
        description="Reference to Key Vault or another secret manager. Raw credentials are not accepted.",
    )


class SourceSystemOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    system_type: str
    connection_type: str | None
    status: str
    secret_reference: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: str
    tenant_id: str
    job_type: str
    status: str
    message: str | None
    result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MetadataColumnOut(BaseModel):
    id: str
    column_name: str
    data_type: str | None
    is_nullable: bool
    is_primary_key: bool
    is_foreign_key: bool
    null_percentage: float | None
    distinct_count: int | None
    sample_values: list[str] | None

    model_config = {"from_attributes": True}


class MetadataTableOut(BaseModel):
    id: str
    source_system_id: str
    database_name: str | None
    schema_name: str | None
    table_name: str
    row_count: int
    detected_entity: str | None
    columns: list[MetadataColumnOut] = []

    model_config = {"from_attributes": True}


class IssueOut(BaseModel):
    id: str
    table_id: str | None
    column_id: str | None
    issue_type: str
    severity: str
    description: str
    recommendation: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RecommendationOut(BaseModel):
    id: str
    category: str
    title: str
    description: str
    priority: str
    estimated_effort: str
    business_value: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PocAssetOut(BaseModel):
    id: str
    platform: str
    asset_type: str
    asset_name: str
    file_path: str
    content: str
    generated_at: datetime

    model_config = {"from_attributes": True}


class DocumentUpload(BaseModel):
    file_name: str
    document_type: str = "Funding agreement"
    target_schema: dict[str, Any] = Field(default_factory=lambda: default_document_schema())


def default_document_schema() -> dict[str, Any]:
    return {
        "table_name": "funding_agreement",
        "columns": [
            "service_name",
            "program_name",
            "person_in_charge",
            "funder_name",
            "approved_funding_fy25",
            "approved_funding_fy26",
            "approved_funding_fy27",
            "total_funding",
        ],
    }


class DocumentOut(BaseModel):
    id: str
    file_name: str
    document_type: str
    status: str
    target_schema: dict[str, Any] | None
    extracted_fields: dict[str, Any] | None
    confidence_score: float | None
    approved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardSnapshot(BaseModel):
    metrics: dict[str, int | float]
    source_systems: list[SourceSystemOut]
    data_quality_scores: dict[str, int]
    entities: list[dict[str, Any]]
    pain_points: list[dict[str, Any]]
    recommendations: list[RecommendationOut]
    poc_assets: list[PocAssetOut]
    mermaid: str


class CopilotQuestion(BaseModel):
    question: str


class CopilotAnswer(BaseModel):
    answer: str
