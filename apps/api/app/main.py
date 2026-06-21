import json

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import Base, engine, get_db
from app.models import DataQualityIssue, Document, Job, MetadataTable, PocAsset, Recommendation, SourceSystem, Tenant
from app.schemas import (
    DashboardSnapshot,
    CopilotAnswer,
    CopilotQuestion,
    DocumentOut,
    DocumentUpload,
    IssueOut,
    JobOut,
    MetadataTableOut,
    PocAssetOut,
    RecommendationOut,
    SourceSystemCreate,
    SourceSystemOut,
    default_document_schema,
)
from app.security import get_tenant_id
from app.services.audit import audit
from app.services.bedrock import invoke_bedrock_text
from app.services.documents import approve_document, extract_document
from app.services.graph import graph_entities, graph_issues, graph_lineage
from app.services.jobs import enqueue_job
from app.services.profiler import quality_scores, run_profile
from app.services.recommendations import architecture_mermaid, generate_poc_assets, generate_recommendations
from app.services.scanner import run_metadata_scan
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


def ensure_tenant(db: Session, tenant_id: str) -> None:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        db.add(Tenant(id=tenant_id, name="Local Tenant", industry="Unknown"))
        db.commit()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/api/dashboard", response_model=DashboardSnapshot)
def dashboard(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> DashboardSnapshot:
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
def create_source_system(payload: SourceSystemCreate, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> SourceSystem:
    ensure_tenant(db, tenant_id)
    if payload.secret_reference and not payload.secret_reference.startswith(("kv://", "vault://", "secret://", "env://", "sqlite://")):
        raise HTTPException(status_code=400, detail="Provide a secret reference, not raw credentials")
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
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> SourceSystem:
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
def list_source_systems(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[SourceSystem]:
    return db.scalars(select(SourceSystem).where(SourceSystem.tenant_id == tenant_id).order_by(SourceSystem.created_at.desc())).all()


@app.get("/api/source-systems/{source_system_id}", response_model=SourceSystemOut)
def get_source_system(source_system_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> SourceSystem:
    source = db.get(SourceSystem, source_system_id)
    if source is None or source.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Source system not found")
    return source


@app.delete("/api/source-systems/{source_system_id}")
def delete_source_system(source_system_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict[str, str]:
    source = db.get(SourceSystem, source_system_id)
    if source is None or source.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Source system not found")
    db.delete(source)
    audit(db, tenant_id, "source.delete", {"source_system_id": source_system_id})
    db.commit()
    return {"status": "deleted"}


@app.post("/api/source-systems/{source_system_id}/scan", response_model=JobOut)
def scan_source_system(source_system_id: str, background_tasks: BackgroundTasks, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> Job:
    return enqueue_job(
        background_tasks,
        db,
        tenant_id,
        "metadata_scan",
        "Metadata scan queued",
        lambda task_db, task_tenant_id, _job_id: run_metadata_scan(task_db, task_tenant_id, source_system_id),
    )


@app.get("/api/scans/{scan_id}/status", response_model=JobOut)
def scan_status(scan_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> Job:
    return get_job_or_404(db, tenant_id, scan_id)


@app.get("/api/scans/{scan_id}/results")
def scan_results(scan_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    job = get_job_or_404(db, tenant_id, scan_id)
    tables = db.scalars(select(MetadataTable).options(selectinload(MetadataTable.columns)).where(MetadataTable.tenant_id == tenant_id)).all()
    return {"job": JobOut.model_validate(job), "tables": [MetadataTableOut.model_validate(table) for table in tables]}


@app.post("/api/source-systems/{source_system_id}/profile", response_model=JobOut)
def profile_source_system(source_system_id: str, background_tasks: BackgroundTasks, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> Job:
    return enqueue_job(
        background_tasks,
        db,
        tenant_id,
        "data_profile",
        "Data profiling queued",
        lambda task_db, task_tenant_id, _job_id: run_profile(task_db, task_tenant_id, source_system_id),
    )


@app.get("/api/profiles/{profile_id}", response_model=JobOut)
def profile_status(profile_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> Job:
    return get_job_or_404(db, tenant_id, profile_id)


@app.post("/api/documents/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(default="Funding agreement"),
    target_schema_json: str | None = Form(default=None),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> Document:
    ensure_tenant(db, tenant_id)
    await save_uploaded_file(file, tenant_id, "documents")
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
    document = Document(tenant_id=tenant_id, **document_payload.model_dump())
    db.add(document)
    audit(db, tenant_id, "document.upload", {"file_name": document.file_name})
    db.commit()
    db.refresh(document)
    return document


@app.post("/api/documents/{document_id}/extract")
def document_extract(document_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    try:
        return extract_document(db, tenant_id, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/documents/{document_id}/extraction-result", response_model=DocumentOut)
def document_result(document_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@app.post("/api/documents/{document_id}/approve", response_model=DocumentOut)
def document_approve(document_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> Document:
    try:
        return approve_document(db, tenant_id, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/graph/entities")
def get_graph_entities(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return graph_entities(db, tenant_id)


@app.get("/api/graph/entity/{entity_id}")
def get_graph_entity(entity_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    entities = graph_entities(db, tenant_id)
    for entity in entities:
        if entity["id"] == entity_id:
            return entity
    raise HTTPException(status_code=404, detail="Graph entity not found")


@app.get("/api/graph/lineage/{entity_id}")
def get_lineage(entity_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return graph_lineage(db, tenant_id, entity_id)


@app.get("/api/graph/issues")
def get_graph_issues(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return graph_issues(db, tenant_id)


@app.post("/api/agents/analyze", response_model=JobOut)
def analyze(background_tasks: BackgroundTasks, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> Job:
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
def recommend(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return generate_recommendations(db, tenant_id)


@app.post("/api/agents/generate-poc")
def generate_poc(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return generate_poc_assets(db, tenant_id)


@app.post("/api/agents/copilot", response_model=CopilotAnswer)
def copilot(payload: CopilotQuestion, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> CopilotAnswer:
    snapshot = dashboard(tenant_id, db).model_dump(mode="json")
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
def agent_job(job_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> Job:
    return get_job_or_404(db, tenant_id, job_id)


@app.post("/api/reports/generate")
def generate_report(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    snapshot = dashboard(tenant_id, db)
    return {"report_id": f"assessment-{tenant_id}", "snapshot": snapshot.model_dump(mode="json")}


@app.get("/api/reports/{report_id}")
def get_report(report_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return {"report_id": report_id, "snapshot": dashboard(tenant_id, db).model_dump(mode="json")}


@app.get("/api/reports/{report_id}/download")
def download_report(report_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return {"report_id": report_id, "format": "json", "content": dashboard(tenant_id, db).model_dump(mode="json")}


@app.get("/api/issues", response_model=list[IssueOut])
def list_issues(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[DataQualityIssue]:
    return db.scalars(select(DataQualityIssue).where(DataQualityIssue.tenant_id == tenant_id)).all()


@app.get("/api/recommendations", response_model=list[RecommendationOut])
def list_recommendations(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[Recommendation]:
    return db.scalars(select(Recommendation).where(Recommendation.tenant_id == tenant_id)).all()


@app.get("/api/poc-assets", response_model=list[PocAssetOut])
def list_poc_assets(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[PocAsset]:
    return db.scalars(select(PocAsset).where(PocAsset.tenant_id == tenant_id)).all()


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
