from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ColumnMetadata:
    column_name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    sample_values: list[str] | None = None


@dataclass(frozen=True)
class TableMetadata:
    database_name: str
    schema_name: str
    table_name: str
    row_count: int
    columns: list[ColumnMetadata]
    row_count_is_estimated: bool = True
    owner: str | None = None
    steward: str | None = None
    source_freshness_at: datetime | None = None


@dataclass(frozen=True)
class IndexMetadata:
    table_name: str
    index_name: str
    column_names: list[str]
    is_unique: bool = False


@dataclass(frozen=True)
class RelationshipMetadata:
    from_table: str
    from_columns: list[str]
    to_table: str
    to_columns: list[str]
    from_schema: str | None = None
    to_schema: str | None = None
    relationship_type: str = "FOREIGN_KEY"


@dataclass(frozen=True)
class ViewMetadata:
    database_name: str | None
    schema_name: str | None
    view_name: str
    definition: str | None = None


@dataclass(frozen=True)
class ProcedureMetadata:
    schema_name: str | None
    procedure_name: str
    definition: str | None = None


@dataclass(frozen=True)
class ProfileConfig:
    row_limit: int
    max_columns: int
    timeout_seconds: int


class BaseConnector(ABC):
    def __init__(self, source_name: str, secret_reference: str | None = None) -> None:
        self.source_name = source_name
        self.secret_reference = secret_reference

    @abstractmethod
    def test_connection(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_schemas(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def list_tables(self, scan_mode: str = "metadata_only") -> list[TableMetadata]:
        raise NotImplementedError

    def list_indexes(self) -> list[IndexMetadata]:
        return []

    def list_relationships(self) -> list[RelationshipMetadata]:
        return []

    def list_views(self) -> list[ViewMetadata]:
        return []

    def list_procedures(self) -> list[ProcedureMetadata]:
        return []

    def profile_columns(self, schema_name: str, table_name: str, columns: list[str], row_count: int, config: ProfileConfig) -> dict[str, dict[str, Any]]:
        return {}
