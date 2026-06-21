from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import DataQualityIssue, MetadataRelationship, MetadataTable, SourceSystem


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
    relationships = db.scalars(select(MetadataRelationship).where(MetadataRelationship.tenant_id == tenant_id)).all()
    for table in tables:
        edges.append({"from": table.source_system_id, "to": table.id, "relationship": "CONTAINS"})
        if table.detected_entity:
            edges.append({"from": table.id, "to": f"entity-{table.detected_entity}", "relationship": "REPRESENTS"})
    for relationship in relationships:
        if relationship.from_table_id and relationship.to_table_id:
            edges.append({"from": relationship.from_table_id, "to": relationship.to_table_id, "relationship": relationship.relationship_type})
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


def sync_neo4j_graph(db: Session, tenant_id: str) -> None:
    settings = get_settings()
    if not settings.neo4j_uri or not settings.neo4j_user or not settings.neo4j_password:
        return
    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import Neo4jError, ServiceUnavailable
    except ImportError:
        return

    driver = None
    try:
        sources = db.scalars(select(SourceSystem).where(SourceSystem.tenant_id == tenant_id)).all()
        tables = db.scalars(select(MetadataTable).where(MetadataTable.tenant_id == tenant_id)).all()
        relationships = db.scalars(select(MetadataRelationship).where(MetadataRelationship.tenant_id == tenant_id)).all()
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        with driver.session() as session:
            session.run("MERGE (tenant:Tenant {id: $tenant_id})", tenant_id=tenant_id)
            for source in sources:
                session.run(
                    """
                    MATCH (tenant:Tenant {id: $tenant_id})
                    MERGE (system:SourceSystem {id: $source_id})
                    SET system.name = $name, system.system_type = $system_type
                    MERGE (tenant)-[:OWNS]->(system)
                    """,
                    tenant_id=tenant_id,
                    source_id=source.id,
                    name=source.name,
                    system_type=source.system_type,
                )
            for table in tables:
                session.run(
                    """
                    MATCH (system:SourceSystem {id: $source_id})
                    MERGE (table:Table {id: $table_id})
                    SET table.tenant_id = $tenant_id,
                        table.source_system_id = $source_id,
                        table.schema_name = $schema_name,
                        table.name = $table_name,
                        table.entity = $entity
                    MERGE (system)-[:CONTAINS]->(table)
                    WITH table
                    FOREACH (_ IN CASE WHEN $entity IS NULL THEN [] ELSE [1] END |
                      MERGE (entity:BusinessEntity {tenant_id: $tenant_id, name: $entity})
                      MERGE (table)-[:REPRESENTS]->(entity)
                    )
                    """,
                    tenant_id=tenant_id,
                    source_id=table.source_system_id,
                    table_id=table.id,
                    schema_name=table.schema_name,
                    table_name=table.table_name,
                    entity=table.detected_entity,
                )
            for relationship in relationships:
                if not relationship.from_table_id or not relationship.to_table_id:
                    continue
                session.run(
                    """
                    MATCH (from_table:Table {tenant_id: $tenant_id, id: $from_table_id})
                    MATCH (to_table:Table {tenant_id: $tenant_id, id: $to_table_id})
                    MERGE (from_table)-[:DEPENDS_ON {type: $relationship_type}]->(to_table)
                    """,
                    tenant_id=tenant_id,
                    from_table_id=relationship.from_table_id,
                    to_table_id=relationship.to_table_id,
                    relationship_type=relationship.relationship_type,
                )
    except (Neo4jError, ServiceUnavailable, OSError):
        return
    finally:
        if driver is not None:
            driver.close()
