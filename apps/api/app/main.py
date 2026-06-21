import json

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import DataQualityIssue, Document, Job, JobLog, MetadataTable, PocAsset, Recommendation, SourceSystem, Tenant, TenantMembership, User
from app.schemas import (
    DashboardSnapshot,
    CopilotAnswer,
    CopilotQuestion,
    CurrentUserOut,
    DocumentOut,
    DocumentUpload,
    IssueOut,
    JobLogOut,
    JobOut,
    LoginRequest,
    MetadataTableOut,
    PocAssetOut,
    RecommendationOut,
    SourceSystemCreate,
    SourceSystemOut,
    TokenOut,
    default_document_schema,
)
from app.security import AuthContext, create_access_token, get_auth_context, require_role, verify_password
from app.services.audit import audit
from app.services.bedrock import invoke_bedrock_text
from app.services.bootstrap import bootstrap_admin_user
from app.services.documents import approve_document, extract_document
from app.services.graph import graph_entities, graph_issues, graph_lineage
from app.services.jobs import enqueue_job, request_job_cancel
from app.services.profiler import quality_scores, run_profile
from app.services.recommendations import architecture_mermaid, generate_poc_assets, generate_recommendations
from app.services.scanner import run_metadata_scan
from app.services.schema_compat import ensure_schema_compat
from app.services.secrets import validate_secret_reference_for_tenant
from app.services.uploads import save_uploaded_file, validate_source_file

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_compat(engine)
    with SessionLocal() as db:
        bootstrap_admin_user(db)


def ensure_tenant(db: Session, tenant_id: str) -> None:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        db.add(Tenant(id=tenant_id, name="Local Tenant", industry="Unknown"))
        db.commit()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.post("/api/auth/login", response_model=TokenOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip(), User.is_active.is_(True)))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    membership_query = select(TenantMembership).where(TenantMembership.user_id == user.id)
    if payload.tenant_id:
        membership_query = membership_query.where(TenantMembership.tenant_id == payload.tenant_id)
    membership = db.scalar(membership_query.order_by(TenantMembership.created_at.asc()))
    if membership is None:
        raise HTTPException(status_code=403, detail="User does not belong to the requested tenant")
    token = create_access_token(user, membership.tenant_id, membership.role)
    return TokenOut(access_token=token, tenant_id=membership.tenant_id, role=membership.role)


@app.get("/api/auth/me", response_model=CurrentUserOut)
def me(context: AuthContext = Depends(get_auth_context)) -> CurrentUserOut:
    return CurrentUserOut(user_id=context.user_id, email=context.email, tenant_id=context.tenant_id, role=context.role)


@app.get("/api/dashboard", response_model=DashboardSnapshot)
def dashboard(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> DashboardSnapshot:
    return dashboard_snapshot(db, context.tenant_id)


def dashboard_snapshot(db: Session, tenant_id: str) -> DashboardSnapshot:
    ensure_tenant(db, tenant_id)
    source_count = db.scalar(select(func.count(SourceSystem.id)).where(SourceSystem.tenant_id == tenant_id)) or 0
    table_count = db.scalar(select(func.count(MetadataTable.id)).where(MetadataTable.tenant_id == tenant_id)) or 0
    issue_count = db.scalar(select(func.count(DataQualityIssue.id)).where(DataQualityIssue.tenant_id == tenant_id)) or 0
    asset_count = db.scalar(select(func.count(PocAsset.id)).where(PocAsset.tenant_id == tenant_id)) or 0
    document_count = db.scalar(select(func.count(Document.id)).where(Document.tenant_id == tenant_id)) or 0
    sources = db.scalars(select(SourceSystem).where(SourceSystem.tenant_id == tenant_id).order_by(SourceSystem.created_at.desc())).all()
    recommendations = db.scalars(select(Recommendation).where(Recommendation.tenant_id == tenant_id)).all()
    assets = db.scalars(select(PocAsset).where(PocAsset.tenant_id == tenant_id)).all()
    pain_points = build_pain_points(db, tenant_id)
    return DashboardSnapshot(
        metrics={
            "systems_connected": source_count,
            "tables_scanned": table_count,
            "issues_detected": issue_count,
            "documents_extracted": document_count,
            "entities_discovered": len({entity["label"] for entity in graph_entities(db, tenant_id) if entity["type"] == "BusinessEntity"}),
            "poc_assets_generated": asset_count,
        },
        source_systems=sources,
        data_quality_scores=quality_scores(db, tenant_id),
        entities=graph_entities(db, tenant_id),
        pain_points=pain_points,
        recommendations=recommendations,
        poc_assets=assets,
        mermaid=assets[0].content if assets else architecture_mermaid(),
    )


@app.post("/api/source-systems", response_model=SourceSystemOut)
def create_source_system(payload: SourceSystemCreate, context: AuthContext = Depends(require_role("analyst")), db: Session = Depends(get_db)) -> SourceSystem:
    tenant_id = context.tenant_id
    ensure_tenant(db, tenant_id)
    if payload.secret_reference and not payload.secret_reference.startswith(("kv://", "vault://", "secret://", "env://", "sqlite://")):
        raise HTTPException(status_code=400, detail="Provide a secret reference, not raw credentials")
    try:
        validate_secret_reference_for_tenant(payload.secret_reference, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    source = SourceSystem(tenant_id=tenant_id, **payload.model_dump())
    db.add(source)
    audit(db, tenant_id, "source.create", {"name": source.name, "system_type": source.system_type})
    db.commit()
    db.refresh(source)
    return source


@app.post("/api/source-systems/upload-file", response_model=SourceSystemOut)
async def upload_source_file(
    system_type: str = Form(...),
    sheet_or_delimiter: str | None = Form(default=None),
    file: UploadFile = File(...),
    context: AuthContext = Depends(require_role("analyst")),
    db: Session = Depends(get_db),
) -> SourceSystem:
    tenant_id = context.tenant_id
    ensure_tenant(db, tenant_id)
    validate_source_file(system_type, file.filename or "")
    stored_path = await save_uploaded_file(file, tenant_id, "sources")
    source = SourceSystem(
        tenant_id=tenant_id,
        name=f"{file.filename} ({system_type})",
        system_type=system_type,
        connection_type="file-upload",
        secret_reference=f"file://{stored_path}",
        status="registered",
    )
    db.add(source)
    audit(db, tenant_id, "source.file_upload", {"file_name": file.filename, "system_type": system_type, "options": sheet_or_delimiter})
    db.commit()
    db.refresh(source)
    return source


@app.get("/api/source-systems", response_model=list[SourceSystemOut])
def list_source_systems(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> list[SourceSystem]:
    tenant_id = context.tenant_id
    return db.scalars(select(SourceSystem).where(SourceSystem.tenant_id == tenant_id).order_by(SourceSystem.created_at.desc())).all()


@app.get("/api/source-systems/{source_system_id}", response_model=SourceSystemOut)
def get_source_system(source_system_id: str, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> SourceSystem:
    tenant_id = context.tenant_id
    source = db.get(SourceSystem, source_system_id)
    if source is None or source.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Source system not found")
    return source


@app.delete("/api/source-systems/{source_system_id}")
def delete_source_system(source_system_id: str, context: AuthContext = Depends(require_role("admin")), db: Session = Depends(get_db)) -> dict[str, str]:
    tenant_id = context.tenant_id
    source = db.get(SourceSystem, source_system_id)
    if source is None or source.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Source system not found")
    db.delete(source)
    audit(db, tenant_id, "source.delete", {"source_system_id": source_system_id})
    db.commit()
    return {"status": "deleted"}


@app.post("/api/source-systems/{source_system_id}/scan", response_model=JobOut)
def scan_source_system(source_system_id: str, background_tasks: BackgroundTasks, context: AuthContext = Depends(require_role("analyst")), db: Session = Depends(get_db)) -> Job:
    tenant_id = context.tenant_id
    return enqueue_job(
        background_tasks,
        db,
        tenant_id,
        "metadata_scan",
        "Metadata scan queued",
        lambda task_db, task_tenant_id, _job_id: run_metadata_scan(task_db, task_tenant_id, source_system_id),
    )


@app.get("/api/scans/{scan_id}/status", response_model=JobOut)
def scan_status(scan_id: str, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> Job:
    tenant_id = context.tenant_id
    return get_job_or_404(db, tenant_id, scan_id)


@app.get("/api/scans/{scan_id}/results")
def scan_results(scan_id: str, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict:
    tenant_id = context.tenant_id
    job = get_job_or_404(db, tenant_id, scan_id)
    tables = db.scalars(select(MetadataTable).options(selectinload(MetadataTable.columns)).where(MetadataTable.tenant_id == tenant_id)).all()
    return {"job": JobOut.model_validate(job), "tables": [MetadataTableOut.model_validate(table) for table in tables]}


@app.post("/api/source-systems/{source_system_id}/profile", response_model=JobOut)
def profile_source_system(source_system_id: str, background_tasks: BackgroundTasks, context: AuthContext = Depends(require_role("analyst")), db: Session = Depends(get_db)) -> Job:
    tenant_id = context.tenant_id
    return enqueue_job(
        background_tasks,
        db,
        tenant_id,
        "data_profile",
        "Data profiling queued",
        lambda task_db, task_tenant_id, _job_id: run_profile(task_db, task_tenant_id, source_system_id),
    )


@app.get("/api/profiles/{profile_id}", response_model=JobOut)
def profile_status(profile_id: str, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> Job:
    tenant_id = context.tenant_id
    return get_job_or_404(db, tenant_id, profile_id)


@app.post("/api/documents/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(default="Funding agreement"),
    target_schema_json: str | None = Form(default=None),
    context: AuthContext = Depends(require_role("analyst")),
    db: Session = Depends(get_db),
) -> Document:
    tenant_id = context.tenant_id
    ensure_tenant(db, tenant_id)
    stored_path = await save_uploaded_file(file, tenant_id, "documents")
    target_schema = default_document_schema()
    if target_schema_json:
        try:
            parsed_schema = json.loads(target_schema_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="target_schema_json must be valid JSON") from exc
        if not isinstance(parsed_schema, dict):
            raise HTTPException(status_code=400, detail="target_schema_json must be a JSON object")
        target_schema = parsed_schema
    document_payload = DocumentUpload(file_name=file.filename or "uploaded-document", document_type=document_type, target_schema=target_schema)
    document = Document(tenant_id=tenant_id, file_path=str(stored_path), **document_payload.model_dump())
    db.add(document)
    audit(db, tenant_id, "document.upload", {"file_name": document.file_name})
    db.commit()
    db.refresh(document)
    return document


@app.post("/api/documents/{document_id}/extract")
def document_extract(document_id: str, context: AuthContext = Depends(require_role("analyst")), db: Session = Depends(get_db)) -> dict:
    try:
        return extract_document(db, context.tenant_id, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/documents/{document_id}/extraction-result", response_model=DocumentOut)
def document_result(document_id: str, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> Document:
    tenant_id = context.tenant_id
    document = db.get(Document, document_id)
    if document is None or document.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@app.post("/api/documents/{document_id}/approve", response_model=DocumentOut)
def document_approve(document_id: str, context: AuthContext = Depends(require_role("analyst")), db: Session = Depends(get_db)) -> Document:
    try:
        return approve_document(db, context.tenant_id, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/graph/entities")
def get_graph_entities(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> list[dict]:
    return graph_entities(db, context.tenant_id)


@app.get("/api/graph/entity/{entity_id}")
def get_graph_entity(entity_id: str, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict:
    entities = graph_entities(db, context.tenant_id)
    for entity in entities:
        if entity["id"] == entity_id:
            return entity
    raise HTTPException(status_code=404, detail="Graph entity not found")


@app.get("/api/graph/lineage/{entity_id}")
def get_lineage(entity_id: str, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict:
    return graph_lineage(db, context.tenant_id, entity_id)


@app.get("/api/graph/issues")
def get_graph_issues(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> list[dict]:
    return graph_issues(db, context.tenant_id)


@app.post("/api/agents/analyze", response_model=JobOut)
def analyze(background_tasks: BackgroundTasks, context: AuthContext = Depends(require_role("analyst")), db: Session = Depends(get_db)) -> Job:
    tenant_id = context.tenant_id
    def task(task_db: Session, task_tenant_id: str, _job_id: str) -> dict:
        sources = task_db.scalars(select(SourceSystem).where(SourceSystem.tenant_id == task_tenant_id)).all()
        for source in sources:
            run_metadata_scan(task_db, task_tenant_id, source.id)
            run_profile(task_db, task_tenant_id, source.id)
        generate_recommendations(task_db, task_tenant_id)
        generate_poc_assets(task_db, task_tenant_id)
        return {"sources_analyzed": len(sources)}

    return enqueue_job(background_tasks, db, tenant_id, "agent_analysis", "Assessment workflow queued", task)


@app.post("/api/agents/recommend")
def recommend(context: AuthContext = Depends(require_role("analyst")), db: Session = Depends(get_db)) -> dict:
    return generate_recommendations(db, context.tenant_id)


@app.post("/api/agents/generate-poc")
def generate_poc(context: AuthContext = Depends(require_role("analyst")), db: Session = Depends(get_db)) -> dict:
    return generate_poc_assets(db, context.tenant_id)


@app.post("/api/agents/copilot", response_model=CopilotAnswer)
def copilot(payload: CopilotQuestion, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> CopilotAnswer:
    tenant_id = context.tenant_id
    snapshot = dashboard_snapshot(db, tenant_id).model_dump(mode="json")
    prompt = f"""
You are the AI copilot for an enterprise data assessment portal.
Answer the user's question using only this assessment snapshot. Be concise and practical.

Question: {payload.question}
Snapshot JSON: {json.dumps(snapshot, ensure_ascii=False)}
""".strip()
    answer = invoke_bedrock_text(prompt, max_tokens=700)
    if not answer:
        raise HTTPException(status_code=503, detail="AWS Bedrock is not configured or did not return an answer")
    audit(db, tenant_id, "agent.copilot", {"question": payload.question})
    db.commit()
    return CopilotAnswer(answer=answer)


@app.get("/api/agents/jobs/{job_id}", response_model=JobOut)
def agent_job(job_id: str, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> Job:
    return get_job_or_404(db, context.tenant_id, job_id)


@app.post("/api/agents/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, context: AuthContext = Depends(require_role("analyst")), db: Session = Depends(get_db)) -> Job:
    try:
        return request_job_cancel(db, context.tenant_id, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/agents/jobs/{job_id}/logs", response_model=list[JobLogOut])
def job_logs(job_id: str, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> list[JobLog]:
    get_job_or_404(db, context.tenant_id, job_id)
    return db.scalars(select(JobLog).where(JobLog.tenant_id == context.tenant_id, JobLog.job_id == job_id).order_by(JobLog.created_at.asc())).all()


@app.post("/api/reports/generate")
def generate_report(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict:
    tenant_id = context.tenant_id
    snapshot = dashboard_snapshot(db, tenant_id)
    return {"report_id": f"assessment-{tenant_id}", "snapshot": snapshot.model_dump(mode="json")}


@app.get("/api/reports/{report_id}")
def get_report(report_id: str, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict:
    return {"report_id": report_id, "snapshot": dashboard_snapshot(db, context.tenant_id).model_dump(mode="json")}


@app.get("/api/reports/{report_id}/download")
def download_report(report_id: str, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict:
    return {"report_id": report_id, "format": "json", "content": dashboard_snapshot(db, context.tenant_id).model_dump(mode="json")}


@app.get("/api/issues", response_model=list[IssueOut])
def list_issues(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> list[DataQualityIssue]:
    return db.scalars(select(DataQualityIssue).where(DataQualityIssue.tenant_id == context.tenant_id)).all()


@app.get("/api/recommendations", response_model=list[RecommendationOut])
def list_recommendations(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> list[Recommendation]:
    return db.scalars(select(Recommendation).where(Recommendation.tenant_id == context.tenant_id)).all()


@app.get("/api/poc-assets", response_model=list[PocAssetOut])
def list_poc_assets(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> list[PocAsset]:
    return db.scalars(select(PocAsset).where(PocAsset.tenant_id == context.tenant_id)).all()


def get_job_or_404(db: Session, tenant_id: str, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def build_pain_points(db: Session, tenant_id: str) -> list[dict]:
    issues = db.scalars(select(DataQualityIssue).where(DataQualityIssue.tenant_id == tenant_id)).all()
    return [
        {
            "pain_point": issue.description,
            "severity": issue.severity,
            "affected_systems": ["Contoso ERP"],
            "affected_entities": ["Customer", "Invoice", "Funding"],
            "business_impact": "Dashboard and POC outputs may be delayed or trusted less by stakeholders.",
            "recommended_action": issue.recommendation,
        }
        for issue in issues[:6]
    ]
