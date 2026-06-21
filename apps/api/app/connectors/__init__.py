from app.connectors.file_connector import FileConnector
from app.connectors.sqlalchemy_connector import SqlAlchemyConnector
from app.models import SourceSystem

__all__ = ["FileConnector", "SqlAlchemyConnector", "connector_for_source"]


def connector_for_source(source: SourceSystem):
	source_type = source.system_type.lower()
	if source_type in {"postgresql", "postgres", "sqlite", "mysql", "sql server", "mssql", "oracle"}:
		return SqlAlchemyConnector(source.name, source.secret_reference)
	if source_type in {"csv", "excel", "json", "parquet"}:
		return FileConnector(source.name, source.system_type, source.secret_reference)
	raise ValueError(f"No connector is configured for {source.system_type}")
