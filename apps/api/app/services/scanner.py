from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.connectors import connector_for_source
from app.models import DataQualityIssue, MetadataColumn, MetadataIndex, MetadataProcedure, MetadataRelationship, MetadataTable, MetadataView, SourceSystem
from app.services.audit import audit
from app.services.entity_discovery import detect_entity
from app.services.graph import sync_neo4j_graph


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
        db.execute(delete(MetadataIndex).where(MetadataIndex.tenant_id == tenant_id, MetadataIndex.table_id.in_(existing_tables)))
        db.execute(delete(MetadataColumn).where(MetadataColumn.tenant_id == tenant_id, MetadataColumn.table_id.in_(existing_tables)))
        db.execute(delete(MetadataTable).where(MetadataTable.tenant_id == tenant_id, MetadataTable.id.in_(existing_tables)))
    db.execute(delete(MetadataRelationship).where(MetadataRelationship.tenant_id == tenant_id, MetadataRelationship.source_system_id == source_system_id))
    db.execute(delete(MetadataView).where(MetadataView.tenant_id == tenant_id, MetadataView.source_system_id == source_system_id))
    db.execute(delete(MetadataProcedure).where(MetadataProcedure.tenant_id == tenant_id, MetadataProcedure.source_system_id == source_system_id))

    connector = connector_for_source(source)
    if not connector.test_connection():
        raise ValueError("Unable to connect using provided secret reference")

    table_count = 0
    column_count = 0
    table_ids_by_name: dict[str, str] = {}
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
            owner=discovered.owner,
            steward=discovered.steward,
            source_freshness_at=discovered.source_freshness_at,
        )
        db.add(table)
        db.flush()
        table_ids_by_name[discovered.table_name] = table.id
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

    index_count = 0
    for discovered_index in connector.list_indexes():
        table_id = table_ids_by_name.get(discovered_index.table_name)
        if not table_id:
            continue
        db.add(
            MetadataIndex(
                tenant_id=tenant_id,
                table_id=table_id,
                index_name=discovered_index.index_name,
                column_names=discovered_index.column_names,
                is_unique=discovered_index.is_unique,
            )
        )
        index_count += 1

    relationship_count = 0
    for relationship in connector.list_relationships():
        db.add(
            MetadataRelationship(
                tenant_id=tenant_id,
                source_system_id=source.id,
                from_table=relationship.from_table,
                from_columns=relationship.from_columns,
                to_table=relationship.to_table,
                to_columns=relationship.to_columns,
                relationship_type=relationship.relationship_type,
            )
        )
        relationship_count += 1

    view_count = 0
    for view in connector.list_views():
        db.add(
            MetadataView(
                tenant_id=tenant_id,
                source_system_id=source.id,
                database_name=view.database_name,
                schema_name=view.schema_name,
                view_name=view.view_name,
                definition=view.definition,
            )
        )
        view_count += 1

    procedure_count = 0
    for procedure in connector.list_procedures():
        db.add(
            MetadataProcedure(
                tenant_id=tenant_id,
                source_system_id=source.id,
                schema_name=procedure.schema_name,
                procedure_name=procedure.procedure_name,
                definition=procedure.definition,
            )
        )
        procedure_count += 1

    source.status = "scanned"
    audit(
        db,
        tenant_id,
        "metadata.scan",
        {
            "source_system_id": source.id,
            "tables": table_count,
            "columns": column_count,
            "indexes": index_count,
            "relationships": relationship_count,
            "views": view_count,
            "procedures": procedure_count,
        },
    )
    db.commit()
    sync_neo4j_graph(db, tenant_id)
    return {
        "source_system_id": source.id,
        "tables_scanned": table_count,
        "columns_scanned": column_count,
        "indexes_scanned": index_count,
        "relationships_scanned": relationship_count,
        "views_scanned": view_count,
        "procedures_scanned": procedure_count,
    }
