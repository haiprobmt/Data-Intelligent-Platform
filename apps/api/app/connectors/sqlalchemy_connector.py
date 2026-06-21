from typing import Any

from sqlalchemy import MetaData, Table, create_engine, func, inspect, select
from sqlalchemy.engine import Engine

from app.connectors.base import BaseConnector, ColumnMetadata, IndexMetadata, ProfileConfig, RelationshipMetadata, TableMetadata, ViewMetadata
from app.services.secrets import resolve_secret_reference


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

    def list_tables(self, scan_mode: str = "metadata_only") -> list[TableMetadata]:
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
                        row_count=self._row_count(table_name, table_schema, scan_mode),
                        row_count_is_estimated=scan_mode == "metadata_only" and self.engine.dialect.name != "sqlite",
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

    def list_indexes(self) -> list[IndexMetadata]:
        inspector = inspect(self.engine)
        indexes: list[IndexMetadata] = []
        for schema in self.list_schemas():
            table_schema = None if self.engine.dialect.name == "sqlite" else schema
            for table_name in inspector.get_table_names(schema=table_schema):
                for index in inspector.get_indexes(table_name, schema=table_schema):
                    indexes.append(
                        IndexMetadata(
                            table_name=table_name,
                            index_name=str(index.get("name") or "unnamed_index"),
                            column_names=list(index.get("column_names") or []),
                            is_unique=bool(index.get("unique", False)),
                        )
                    )
        return indexes

    def list_relationships(self) -> list[RelationshipMetadata]:
        inspector = inspect(self.engine)
        relationships: list[RelationshipMetadata] = []
        for schema in self.list_schemas():
            table_schema = None if self.engine.dialect.name == "sqlite" else schema
            for table_name in inspector.get_table_names(schema=table_schema):
                for foreign_key in inspector.get_foreign_keys(table_name, schema=table_schema):
                    referred_table = foreign_key.get("referred_table")
                    if not referred_table:
                        continue
                    relationships.append(
                        RelationshipMetadata(
                            from_table=table_name,
                            from_columns=list(foreign_key.get("constrained_columns") or []),
                            to_table=str(referred_table),
                            to_columns=list(foreign_key.get("referred_columns") or []),
                            from_schema=schema,
                            to_schema=str(foreign_key.get("referred_schema") or schema),
                        )
                    )
        return relationships

    def list_views(self) -> list[ViewMetadata]:
        inspector = inspect(self.engine)
        views: list[ViewMetadata] = []
        database_name = self.engine.url.database or self.source_name
        for schema in self.list_schemas():
            table_schema = None if self.engine.dialect.name == "sqlite" else schema
            for view_name in inspector.get_view_names(schema=table_schema):
                views.append(
                    ViewMetadata(
                        database_name=database_name,
                        schema_name=schema,
                        view_name=view_name,
                        definition=inspector.get_view_definition(view_name, schema=table_schema),
                    )
                )
        return views

    def profile_columns(self, schema_name: str, table_name: str, columns: list[str], row_count: int, config: ProfileConfig) -> dict[str, dict[str, Any]]:
        table_schema = None if self.engine.dialect.name == "sqlite" else schema_name
        table = Table(table_name, MetaData(), schema=table_schema, autoload_with=self.engine)
        selected_columns = [column for column in columns[: config.max_columns] if column in table.c]
        sample = select(table).limit(config.row_limit).subquery()
        profiles: dict[str, dict[str, Any]] = {}
        with self.engine.connect().execution_options(timeout=config.timeout_seconds) as connection:
            self._apply_statement_timeout(connection, config.timeout_seconds)
            sampled_count = int(connection.execute(select(func.count()).select_from(sample)).scalar_one() or 0)
            for column_name in selected_columns:
                column = sample.c[column_name]
                null_count = connection.execute(select(func.count()).select_from(sample).where(column.is_(None))).scalar_one()
                distinct_count = connection.execute(select(func.count(func.distinct(column))).select_from(sample)).scalar_one()
                profiles[column_name] = {
                    "null_percentage": round((null_count / sampled_count) * 100, 2) if sampled_count else 0,
                    "distinct_count": int(distinct_count or 0),
                    "sampled_row_count": sampled_count,
                }
        return profiles

    def _apply_statement_timeout(self, connection, timeout_seconds: int) -> None:
        timeout_ms = max(1, timeout_seconds) * 1000
        dialect = self.engine.dialect.name
        if dialect == "postgresql":
            connection.exec_driver_sql("SET statement_timeout = %s", (timeout_ms,))
        elif dialect == "mysql":
            connection.exec_driver_sql("SET SESSION MAX_EXECUTION_TIME=%s", (timeout_ms,))

    def _row_count(self, table_name: str, schema_name: str | None, scan_mode: str) -> int:
        if scan_mode == "metadata_only" and self.engine.dialect.name != "sqlite":
            approximate = self._approximate_row_count(table_name, schema_name)
            if approximate is not None:
                return approximate
            return 0
        table = Table(table_name, MetaData(), schema=schema_name, autoload_with=self.engine)
        with self.engine.connect() as connection:
            return int(connection.execute(select(func.count()).select_from(table)).scalar_one() or 0)

    def _approximate_row_count(self, table_name: str, schema_name: str | None) -> int | None:
        dialect = self.engine.dialect.name
        with self.engine.connect() as connection:
            if dialect == "postgresql":
                qualified = f"{schema_name}.{table_name}" if schema_name else table_name
                return int(connection.exec_driver_sql("select coalesce(reltuples, 0)::bigint from pg_class where oid = %s::regclass", (qualified,)).scalar() or 0)
            if dialect == "mysql":
                return int(
                    connection.exec_driver_sql(
                        "select coalesce(table_rows, 0) from information_schema.tables where table_schema = database() and table_name = %s",
                        (table_name,),
                    ).scalar()
                    or 0
                )
            if dialect in {"mssql", "sqlserver"}:
                return int(
                    connection.exec_driver_sql(
                        "select coalesce(sum(row_count), 0) from sys.dm_db_partition_stats where object_id = object_id(?) and index_id in (0,1)",
                        (table_name,),
                    ).scalar()
                    or 0
                )
            if dialect == "oracle":
                return int(
                    connection.exec_driver_sql("select coalesce(num_rows, 0) from all_tables where table_name = :name", {"name": table_name.upper()}).scalar()
                    or 0
                )
        return None


def resolve_connection_url(secret_reference: str | None) -> str:
    return resolve_secret_reference(secret_reference)