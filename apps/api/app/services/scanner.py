from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.connectors import connector_for_source
from app.models import DataQualityIssue, MetadataColumn, MetadataTable, SourceSystem
from app.services.audit import audit
from app.services.entity_discovery import detect_entity


def run_metadata_scan(db: Session, tenant_id: str, source_system_id: str) -> dict:
    source = db.scalar(
        select(SourceSystem).where(SourceSystem.id == source_system_id, SourceSystem.tenant_id == tenant_id)
    )
    if source is None:
        raise ValueError("Source system not found for tenant")

    existing_tables = db.scalars(
        select(MetadataTable.id).where(
            MetadataTable.tenant_id == tenant_id,
            MetadataTable.source_system_id == source_system_id,
        )
    ).all()
    if existing_tables:
        db.execute(delete(DataQualityIssue).where(DataQualityIssue.tenant_id == tenant_id, DataQualityIssue.table_id.in_(existing_tables)))
        db.execute(delete(MetadataColumn).where(MetadataColumn.tenant_id == tenant_id, MetadataColumn.table_id.in_(existing_tables)))
        db.execute(delete(MetadataTable).where(MetadataTable.tenant_id == tenant_id, MetadataTable.id.in_(existing_tables)))

    connector = connector_for_source(source)
    if not connector.test_connection():
        raise ValueError("Unable to connect using provided secret reference")

    table_count = 0
    column_count = 0
    for discovered in connector.list_tables():
        entity = detect_entity(discovered.table_name, [column.column_name for column in discovered.columns])
        table = MetadataTable(
            tenant_id=tenant_id,
            source_system_id=source.id,
            database_name=discovered.database_name,
            schema_name=discovered.schema_name,
            table_name=discovered.table_name,
            row_count=discovered.row_count,
            detected_entity=entity,
        )
        db.add(table)
        db.flush()
        table_count += 1

        for discovered_column in discovered.columns:
            db.add(
                MetadataColumn(
                    tenant_id=tenant_id,
                    table_id=table.id,
                    column_name=discovered_column.column_name,
                    data_type=discovered_column.data_type,
                    is_nullable=discovered_column.is_nullable,
                    is_primary_key=discovered_column.is_primary_key,
                    is_foreign_key=discovered_column.is_foreign_key,
                    sample_values=discovered_column.sample_values,
                )
            )
            column_count += 1

    source.status = "scanned"
    audit(db, tenant_id, "metadata.scan", {"source_system_id": source.id, "tables": table_count, "columns": column_count})
    db.commit()
    return {"source_system_id": source.id, "tables_scanned": table_count, "columns_scanned": column_count}
