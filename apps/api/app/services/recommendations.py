from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DataQualityIssue, MetadataTable, PocAsset, Recommendation
from app.services.audit import audit
from app.services.bedrock import invoke_bedrock_json


def generate_recommendations(db: Session, tenant_id: str) -> dict:
    issues = db.scalars(select(DataQualityIssue).where(DataQualityIssue.tenant_id == tenant_id)).all()
    tables = db.scalars(select(MetadataTable).where(MetadataTable.tenant_id == tenant_id)).all()
    entities = sorted({table.detected_entity for table in tables if table.detected_entity})

    db.execute(delete(Recommendation).where(Recommendation.tenant_id == tenant_id))
    platform = choose_platform(tables)
    bedrock_recommendations = _recommendations_from_bedrock(issues, tables, entities, platform)
    recommendations = [
        Recommendation(tenant_id=tenant_id, **payload) for payload in bedrock_recommendations
    ] if bedrock_recommendations else [
        Recommendation(
            tenant_id=tenant_id,
            category="Fabric readiness" if platform == "Microsoft Fabric" else "Databricks readiness",
            title=f"Use {platform} as the first POC platform",
            description=_platform_reason(platform),
            priority="High",
            estimated_effort="1 week POC",
            business_value="Creates a fast executive-ready path from discovered silos to governed analytics.",
        ),
        Recommendation(
            tenant_id=tenant_id,
            category="Data quality readiness",
            title="Create a Silver quality remediation backlog",
            description=f"The scan found {len(issues)} quality issues across {len(tables)} metadata tables.",
            priority="High" if len(issues) > 3 else "Medium",
            estimated_effort="2-3 sprints",
            business_value="Improves trust in Power BI metrics and downstream AI use cases.",
        ),
        Recommendation(
            tenant_id=tenant_id,
            category="AI readiness",
            title="Prioritize document extraction and RAG over broad automation",
            description="Use human-reviewed extraction for funding agreements and index approved knowledge for consultant search.",
            priority="Medium",
            estimated_effort="1-2 sprints",
            business_value="Turns unstructured agreements into governed data products without skipping review.",
        ),
        Recommendation(
            tenant_id=tenant_id,
            category="Data governance readiness",
            title="Assign data owners to discovered business entities",
            description=f"Detected entities include {', '.join(entities) if entities else 'core operational data'}.",
            priority="Medium",
            estimated_effort="1 sprint",
            business_value="Creates accountability for glossary, access control, and quality decisions.",
        ),
    ]
    db.add_all(recommendations)
    audit(db, tenant_id, "recommendations.generate", {"count": len(recommendations), "platform": platform})
    db.commit()
    return {"recommendations_created": len(recommendations), "platform": platform}


def generate_poc_assets(db: Session, tenant_id: str) -> dict:
    db.execute(delete(PocAsset).where(PocAsset.tenant_id == tenant_id))
    platform = choose_platform(db.scalars(select(MetadataTable).where(MetadataTable.tenant_id == tenant_id)).all())
    mermaid = architecture_mermaid(platform)
    assets = [
        PocAsset(
            tenant_id=tenant_id,
            platform=platform,
            asset_type="Architecture diagram",
            asset_name="Target State Data Platform",
            file_path="generated/architecture/target-state.mmd",
            content=mermaid,
        ),
        PocAsset(
            tenant_id=tenant_id,
            platform=platform,
            asset_type="Notebook template",
            asset_name="Bronze to Silver Quality Notebook",
            file_path="generated/notebooks/bronze_to_silver_quality.py",
            content=bronze_silver_notebook(platform),
        ),
        PocAsset(
            tenant_id=tenant_id,
            platform=platform,
            asset_type="Power BI model",
            asset_name="Executive Assessment Semantic Model",
            file_path="generated/powerbi/semantic-model.md",
            content="Measures: Systems Connected, Tables Scanned, Issues Detected, Overall Quality Score, POC Assets Generated",
        ),
        PocAsset(
            tenant_id=tenant_id,
            platform=platform,
            asset_type="AI/RAG design",
            asset_name="Reviewed Document Knowledge Base",
            file_path="generated/ai/rag-design.md",
            content="Use Amazon Bedrock embeddings and model invocation for approved document extractions, metadata descriptions, tenant-scoped retrieval filters, and evaluation checks.",
        ),
    ]
    db.add_all(assets)
    audit(db, tenant_id, "poc.generate", {"count": len(assets), "platform": platform})
    db.commit()
    return {"assets_created": len(assets), "platform": platform}


def choose_platform(tables: list[MetadataTable]) -> str:
    total_rows = sum(table.row_count for table in tables)
    table_names = " ".join(table.table_name.lower() for table in tables)
    if total_rows > 2_000_000 or "stream" in table_names:
        return "Databricks"
    return "Microsoft Fabric"


def architecture_mermaid(platform: str = "Microsoft Fabric") -> str:
    target = "Fabric Lakehouse" if platform == "Microsoft Fabric" else "Databricks Lakehouse"
    return """flowchart TD
    A[Source Systems] --> B[Connector Layer]
    B --> C[Metadata Discovery]
    B --> D[Document Intelligence]
    C --> E[Knowledge Graph]
    D --> E
    E --> F[AWS Bedrock Agentic Reasoning]
    F --> G[Recommendation Engine]
    G --> H[""" + target + """ POC]
    H --> I[Delivery Portal]
"""


def bronze_silver_notebook(platform: str) -> str:
    return f"""# {platform} Bronze to Silver quality notebook template
from pyspark.sql import functions as F

bronze = spark.table("bronze.customer_master")
silver = (
    bronze
    .dropDuplicates(["customer_id"])
    .withColumn("quality_checked_at", F.current_timestamp())
)
silver.write.mode("overwrite").saveAsTable("silver.customer_master")
"""


def _platform_reason(platform: str) -> str:
    if platform == "Microsoft Fabric":
        return "Customer analytics needs are dashboard-led, data volume is moderate, and Fabric gives the fastest path to Lakehouse, Warehouse, Power BI, and Document Intelligence integration."
    return "The discovered estate suggests high-volume engineering, advanced ML, or streaming needs where Databricks Delta, Unity Catalog, workflows, and vector search fit best."


def _recommendations_from_bedrock(
    issues: list[DataQualityIssue],
    tables: list[MetadataTable],
    entities: list[str],
    platform: str,
) -> list[dict] | None:
    prompt = f"""
You are an enterprise data platform architect using AWS Bedrock for analysis.
Create exactly four recommendations for a data assessment.
Return strict JSON only with this shape:
{{"recommendations": [{{"category": "", "title": "", "description": "", "priority": "High|Medium|Low", "estimated_effort": "", "business_value": ""}}]}}

Context:
- Recommended platform: {platform}
- Tables scanned: {[table.table_name for table in tables]}
- Business entities: {entities}
- Data quality issues: {[{"type": issue.issue_type, "severity": issue.severity, "description": issue.description} for issue in issues[:20]]}

Keep recommendations practical for Fabric, Databricks, Power BI, governed ingestion, and Bedrock-backed AI use cases.
""".strip()
    result = invoke_bedrock_json(prompt, max_tokens=1400)
    if not result or not isinstance(result.get("recommendations"), list):
        return None
    valid: list[dict] = []
    required = {"category", "title", "description", "priority", "estimated_effort", "business_value"}
    for item in result["recommendations"][:4]:
        if isinstance(item, dict) and required.issubset(item):
            valid.append({key: str(item[key]) for key in required})
    return valid or None
