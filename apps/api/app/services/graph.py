from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DataQualityIssue, MetadataTable, SourceSystem


def graph_entities(db: Session, tenant_id: str) -> list[dict]:
    sources = db.scalars(select(SourceSystem).where(SourceSystem.tenant_id == tenant_id)).all()
    tables = db.scalars(select(MetadataTable).where(MetadataTable.tenant_id == tenant_id)).all()
    entities: list[dict] = []
    for source in sources:
        entities.append({"id": source.id, "type": "SourceSystem", "label": source.name})
    for table in tables:
        entities.append({"id": table.id, "type": "Table", "label": table.table_name, "entity": table.detected_entity})
        if table.detected_entity:
            entities.append({"id": f"entity-{table.detected_entity}", "type": "BusinessEntity", "label": table.detected_entity})
    return entities


def graph_lineage(db: Session, tenant_id: str, entity_id: str) -> dict:
    tables = db.scalars(select(MetadataTable).where(MetadataTable.tenant_id == tenant_id)).all()
    nodes = graph_entities(db, tenant_id)
    edges = []
    for table in tables:
        edges.append({"from": table.source_system_id, "to": table.id, "relationship": "CONTAINS"})
        if table.detected_entity:
            edges.append({"from": table.id, "to": f"entity-{table.detected_entity}", "relationship": "REPRESENTS"})
    return {"entity_id": entity_id, "nodes": nodes, "edges": edges}


def graph_issues(db: Session, tenant_id: str) -> list[dict]:
    issues = db.scalars(select(DataQualityIssue).where(DataQualityIssue.tenant_id == tenant_id)).all()
    return [
        {
            "id": issue.id,
            "type": "DataQualityIssue",
            "label": issue.issue_type,
            "severity": issue.severity,
            "impacts": "Executive KPI trust",
            "recommendation": issue.recommendation,
        }
        for issue in issues
    ]
