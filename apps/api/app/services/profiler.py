from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.connectors import connector_for_source
from app.models import DataQualityIssue, MetadataTable, SourceSystem
from app.services.audit import audit


def run_profile(db: Session, tenant_id: str, source_system_id: str) -> dict:
    source = db.scalar(select(SourceSystem).where(SourceSystem.id == source_system_id, SourceSystem.tenant_id == tenant_id))
    if source is None:
        raise ValueError("Source system not found for tenant")

    tables = db.scalars(
        select(MetadataTable)
        .options(selectinload(MetadataTable.columns))
        .where(MetadataTable.tenant_id == tenant_id, MetadataTable.source_system_id == source_system_id)
    ).all()
    if not tables:
        raise ValueError("Run metadata scan before profiling")

    connector = connector_for_source(source)
    table_ids = [table.id for table in tables]
    db.execute(delete(DataQualityIssue).where(DataQualityIssue.tenant_id == tenant_id, DataQualityIssue.table_id.in_(table_ids)))

    issues_created = 0
    for table in tables:
        real_profiles = connector.profile_columns(
            table.schema_name or "main",
            table.table_name,
            [column.column_name for column in table.columns],
            table.row_count,
        )
        has_pk = any(column.is_primary_key for column in table.columns)
        has_freshness = any("updated" in column.column_name.lower() or "modified" in column.column_name.lower() for column in table.columns)

        if not has_pk:
            db.add(
                DataQualityIssue(
                    tenant_id=tenant_id,
                    table_id=table.id,
                    issue_type="Missing primary key",
                    severity="High",
                    description=f"{table.table_name} has no declared primary key.",
                    recommendation="Define a durable business key or surrogate key before Silver layer modeling.",
                )
            )
            issues_created += 1

        if not has_freshness:
            db.add(
                DataQualityIssue(
                    tenant_id=tenant_id,
                    table_id=table.id,
                    issue_type="No CDC column",
                    severity="Medium",
                    description=f"{table.table_name} has no reliable last updated timestamp.",
                    recommendation="Add a CDC-friendly timestamp or use log-based capture for incremental ingestion.",
                )
            )
            issues_created += 1

        if "excel" in table.table_name.lower():
            db.add(
                DataQualityIssue(
                    tenant_id=tenant_id,
                    table_id=table.id,
                    issue_type="Manual Excel dependency",
                    severity="High",
                    description="Finance or operations reporting depends on manually maintained spreadsheet data.",
                    recommendation="Land the tracker in a governed Lakehouse table and add an approval workflow.",
                )
            )
            issues_created += 1

        for column in table.columns:
            column_profile = real_profiles.get(column.column_name, {})
            column.null_percentage = column_profile.get("null_percentage", 0)
            column.distinct_count = column_profile.get("distinct_count", 0)
            if column.null_percentage > 20:
                db.add(
                    DataQualityIssue(
                        tenant_id=tenant_id,
                        table_id=table.id,
                        column_id=column.id,
                        issue_type="High null percentage",
                        severity="Medium",
                        description=f"{column.column_name} in {table.table_name} is {column.null_percentage:.0f}% null.",
                        recommendation="Confirm ownership and validation rules before exposing the field to BI or AI use cases.",
                    )
                )
                issues_created += 1

    source.status = "profiled"
    audit(db, tenant_id, "data.profile", {"source_system_id": source.id, "issues_created": issues_created})
    db.commit()
    return {"source_system_id": source.id, "tables_profiled": len(tables), "issues_created": issues_created, "scores": quality_scores(db, tenant_id)}


def quality_scores(db: Session, tenant_id: str) -> dict[str, int]:
    issue_count = len(db.scalars(select(DataQualityIssue.id).where(DataQualityIssue.tenant_id == tenant_id)).all())
    completeness = max(35, 90 - issue_count * 4)
    uniqueness = max(40, 84 - issue_count * 3)
    freshness = max(30, 82 - issue_count * 5)
    consistency = max(40, 80 - issue_count * 3)
    overall = round((completeness + uniqueness + freshness + consistency) / 4)
    return {
        "completeness": completeness,
        "uniqueness": uniqueness,
        "freshness": freshness,
        "consistency": consistency,
        "overall": overall,
    }
