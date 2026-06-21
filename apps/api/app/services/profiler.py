from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.connectors import connector_for_source
from app.connectors.base import ProfileConfig
from app.models import DataQualityIssue, MetadataTable, SourceSystem
from app.services.audit import audit
from app.services.jobs import update_job_progress
from app.services.secrets import source_secret_reference


def run_profile(db: Session, tenant_id: str, source_system_id: str, job_id: str | None = None) -> dict:
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

    connector = connector_for_source(source, source_secret_reference(db, tenant_id, source))
    settings = get_settings()
    config = ProfileConfig(
        row_limit=settings.profile_default_row_limit,
        max_columns=settings.profile_default_max_columns,
        timeout_seconds=settings.profile_default_timeout_seconds,
    )
    table_ids = [table.id for table in tables]
    db.execute(delete(DataQualityIssue).where(DataQualityIssue.tenant_id == tenant_id, DataQualityIssue.table_id.in_(table_ids)))

    issues_created = 0
    for table_index, table in enumerate(tables, start=1):
        if job_id:
            progress = 10 + round((table_index / max(len(tables), 1)) * 80)
            update_job_progress(db, tenant_id, job_id, progress, f"Profiling {table.table_name}")
        try:
            real_profiles = connector.profile_columns(
                table.schema_name or "main",
                table.table_name,
                [column.column_name for column in table.columns],
                table.row_count,
                config,
            )
        except Exception as exc:
            real_profiles = {}
            db.add(
                DataQualityIssue(
                    tenant_id=tenant_id,
                    table_id=table.id,
                    issue_type="Profiling timeout or error",
                    severity="Medium",
                    description=f"Profiling for {table.table_name} did not complete within safe limits: {exc}",
                    recommendation="Reduce profiling scope, increase timeout, or run profiling from an isolated read replica.",
                )
            )
            issues_created += 1
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

        duplicate_profile = connector.find_duplicate_rows(
            table.schema_name or "main",
            table.table_name,
            [column.column_name for column in table.columns],
            config,
        )
        duplicate_rows = int(duplicate_profile.get("duplicate_rows") or 0)
        if duplicate_rows > 0:
            sampled_row_count = int(duplicate_profile.get("sampled_row_count") or table.row_count or 0)
            duplicate_rate = round((duplicate_rows / sampled_row_count) * 100, 2) if sampled_row_count else 0
            db.add(
                DataQualityIssue(
                    tenant_id=tenant_id,
                    table_id=table.id,
                    issue_type="Duplicate rows detected",
                    severity="High" if not has_pk else "Medium",
                    description=f"{table.table_name} has {duplicate_rows} duplicate sampled row(s) ({duplicate_rate:.1f}% of sampled rows).",
                    recommendation="Define uniqueness rules and deduplicate records before trusted reporting, reconciliation, or AI use cases.",
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
    tables = db.scalars(select(MetadataTable).options(selectinload(MetadataTable.columns)).where(MetadataTable.tenant_id == tenant_id)).all()
    columns = [column for table in tables for column in table.columns]
    if not tables or not columns:
        return {"completeness": 0, "uniqueness": 0, "freshness": 0, "validity": 0, "consistency": 0, "overall": 0}

    completeness = round(100 - (sum(column.null_percentage or 0 for column in columns) / len(columns)))
    uniqueness_scores = []
    for table in tables:
        for column in table.columns:
            if table.row_count <= 0:
                continue
            uniqueness_scores.append(min(100, round(((column.distinct_count or 0) / table.row_count) * 100)))
    uniqueness = round(sum(uniqueness_scores) / len(uniqueness_scores)) if uniqueness_scores else 0
    freshness = round(
        sum(100 if table.source_freshness_at else 70 if any("updated" in column.column_name.lower() or "modified" in column.column_name.lower() for column in table.columns) else 35 for table in tables)
        / len(tables)
    )
    validity = max(0, 100 - len(db.scalars(select(DataQualityIssue.id).where(DataQualityIssue.tenant_id == tenant_id)).all()) * 5)
    consistency = round(sum(100 if any(column.is_foreign_key for column in table.columns) else 70 for table in tables) / len(tables))
    overall = round((completeness + uniqueness + freshness + validity + consistency) / 5)
    return {
        "completeness": completeness,
        "uniqueness": uniqueness,
        "freshness": freshness,
        "validity": validity,
        "consistency": consistency,
        "overall": overall,
    }
