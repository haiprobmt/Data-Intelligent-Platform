from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceSystemCreate(BaseModel):
    name: str
    system_type: str
    connection_type: str = "metadata-only"
    secret_id: str | None = None
    scan_mode: Literal["metadata_only", "light_profile", "full_profile"] = "metadata_only"
    secret_reference: str | None = Field(
        default=None,
        description="Reference to Key Vault or another secret manager. Raw credentials are not accepted.",
    )


class ConnectionSecretCreate(BaseModel):
    name: str
    provider: Literal["env", "azure_key_vault", "sqlite"]
    reference: str


class ConnectionSecretOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    provider: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AssessmentProjectCreate(BaseModel):
    name: str
    industry: str | None = None
    primary_goal: str | None = None


class AssessmentProjectOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    industry: str | None
    primary_goal: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AssessmentProfileIn(BaseModel):
    project_id: str | None = None
    current_microsoft_365_usage: bool = False
    current_power_bi_usage: bool = False
    current_databricks_usage: bool = False
    data_volume: Literal["small", "moderate", "large"] = "moderate"
    streaming_requirement: bool = False
    ml_ai_requirement: bool = False
    budget_sensitivity: Literal["low", "medium", "high"] = "medium"
    engineering_maturity: Literal["low", "medium", "high"] = "medium"
    governance_maturity: Literal["low", "medium", "high"] = "medium"
    deployment_preference: Literal["microsoft", "databricks", "neutral"] = "neutral"


class AssessmentProfileOut(BaseModel):
    fabric_score: int
    databricks_score: int
    recommended_platform: str
    reasoning: list[str]


class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_id: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: str
    role: str


class CurrentUserOut(BaseModel):
    user_id: str
    email: str
    tenant_id: str
    role: str


class SourceSystemOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    system_type: str
    connection_type: str | None
    status: str
    secret_id: str | None
    scan_mode: str
    created_at: datetime

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: str
    tenant_id: str
    job_type: str
    status: str
    message: str | None
    result: dict[str, Any] | None
    progress_percent: int = 0
    cancel_requested: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobLogOut(BaseModel):
    id: str
    job_id: str
    level: str
    message: str
    details: dict[str, Any] | None
    created_at: datetime

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
    row_count_is_estimated: bool
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
    file_path: str | None
    document_type: str
    status: str
    target_schema: dict[str, Any] | None
    extracted_text: str | None
    extracted_fields: dict[str, Any] | None
    extraction_metadata: dict[str, Any] | None
    confidence_score: float | None
    approved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentReviewPatch(BaseModel):
    fields: dict[str, Any]


class DocumentExtractedFieldOut(BaseModel):
    id: str
    document_id: str
    field_name: str
    value: str | None
    confidence: float | None
    reference: str | None
    page_number: int | None
    reviewed_value: str | None
    review_status: str
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
