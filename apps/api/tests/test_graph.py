from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import MetadataRelationship, MetadataTable, SourceSystem
from app.services.graph import graph_lineage


def test_graph_lineage_relationship_edges_use_table_ids():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        tenant_id = "tenant-graph"
        source = SourceSystem(id="source-1", tenant_id=tenant_id, name="Warehouse", system_type="postgresql")
        customer_sales = MetadataTable(
            id="table-sales-customer",
            tenant_id=tenant_id,
            source_system_id="source-1",
            schema_name="sales",
            table_name="customer",
            row_count=10,
        )
        customer_ref = MetadataTable(
            id="table-ref-customer",
            tenant_id=tenant_id,
            source_system_id="source-1",
            schema_name="ref",
            table_name="customer",
            row_count=10,
        )
        relationship = MetadataRelationship(
            tenant_id=tenant_id,
            source_system_id="source-1",
            from_table_id="table-sales-customer",
            from_table="customer",
            from_schema="sales",
            from_columns=["customer_id"],
            to_table_id="table-ref-customer",
            to_table="customer",
            to_schema="ref",
            to_columns=["customer_id"],
        )
        db.add_all([source, customer_sales, customer_ref, relationship])
        db.commit()

        lineage = graph_lineage(db, tenant_id, "table-sales-customer")
        node_ids = {node["id"] for node in lineage["nodes"]}
        relationship_edges = [edge for edge in lineage["edges"] if edge["relationship"] == "FOREIGN_KEY"]

        assert relationship_edges == [
            {"from": "table-sales-customer", "to": "table-ref-customer", "relationship": "FOREIGN_KEY"}
        ]
        assert relationship_edges[0]["from"] in node_ids
        assert relationship_edges[0]["to"] in node_ids
    finally:
        db.close()
