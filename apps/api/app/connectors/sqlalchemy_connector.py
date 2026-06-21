import os
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, func, inspect, select
from sqlalchemy.engine import Engine

from app.connectors.base import BaseConnector, ColumnMetadata, TableMetadata


class SqlAlchemyConnector(BaseConnector):
    def __init__(self, source_name: str, secret_reference: str | None = None) -> None:
        super().__init__(source_name, secret_reference)
        self.connection_url = resolve_connection_url(secret_reference)
        self.engine: Engine = create_engine(self.connection_url)

    def test_connection(self) -> bool:
        with self.engine.connect() as connection:
            connection.execute(select(1))
        return True

    def list_schemas(self) -> list[str]:
        inspector = inspect(self.engine)
        if self.engine.dialect.name == "sqlite":
            return ["main"]
        return [schema for schema in inspector.get_schema_names() if schema not in {"information_schema", "pg_catalog"}]

    def list_tables(self) -> list[TableMetadata]:
        inspector = inspect(self.engine)
        database_name = self.engine.url.database or self.source_name
        tables: list[TableMetadata] = []
        for schema in self.list_schemas():
            table_schema = None if self.engine.dialect.name == "sqlite" else schema
            for table_name in inspector.get_table_names(schema=table_schema):
                columns = inspector.get_columns(table_name, schema=table_schema)
                pk_columns = set(inspector.get_pk_constraint(table_name, schema=table_schema).get("constrained_columns") or [])
                fk_columns = {
                    column
                    for foreign_key in inspector.get_foreign_keys(table_name, schema=table_schema)
                    for column in foreign_key.get("constrained_columns", [])
                }
                tables.append(
                    TableMetadata(
                        database_name=database_name,
                        schema_name=schema,
                        table_name=table_name,
                        row_count=self._row_count(table_name, table_schema),
                        columns=[
                            ColumnMetadata(
                                column_name=column["name"],
                                data_type=str(column.get("type", "unknown")),
                                is_nullable=bool(column.get("nullable", True)),
                                is_primary_key=column["name"] in pk_columns,
                                is_foreign_key=column["name"] in fk_columns,
                                sample_values=None,
                            )
                            for column in columns
                        ],
                    )
                )
        return tables

    def profile_columns(self, schema_name: str, table_name: str, columns: list[str], row_count: int) -> dict[str, dict[str, Any]]:
        table_schema = None if self.engine.dialect.name == "sqlite" else schema_name
        table = Table(table_name, MetaData(), schema=table_schema, autoload_with=self.engine)
        profiles: dict[str, dict[str, Any]] = {}
        with self.engine.connect() as connection:
            for column_name in columns:
                column = table.c[column_name]
                null_count = connection.execute(select(func.count()).select_from(table).where(column.is_(None))).scalar_one()
                distinct_count = connection.execute(select(func.count(func.distinct(column))).select_from(table)).scalar_one()
                profiles[column_name] = {
                    "null_percentage": round((null_count / row_count) * 100, 2) if row_count else 0,
                    "distinct_count": int(distinct_count or 0),
                }
        return profiles

    def _row_count(self, table_name: str, schema_name: str | None) -> int:
        table = Table(table_name, MetaData(), schema=schema_name, autoload_with=self.engine)
        with self.engine.connect() as connection:
            return int(connection.execute(select(func.count()).select_from(table)).scalar_one() or 0)


def resolve_connection_url(secret_reference: str | None) -> str:
    if not secret_reference:
        raise ValueError("A SQL source requires a secret reference such as env://HUB_SOURCE_URL")
    if secret_reference.startswith("env://"):
        variable_name = secret_reference.removeprefix("env://")
        connection_url = os.getenv(variable_name)
        if not connection_url:
            raise ValueError(f"Environment variable {variable_name} is not set")
        return connection_url
    if secret_reference.startswith("sqlite://"):
        return secret_reference
    if secret_reference.startswith(("kv://", "vault://", "secret://")):
        raise ValueError("Vault secret resolution is not configured in this runtime. Use env:// for environment-provided credentials.")
    raise ValueError("Use env://VARIABLE_NAME for credentials or sqlite:///path/to/file.db for SQLite sources")