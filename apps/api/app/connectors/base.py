from abc import ABC, abstractmethod
from dataclasses import dataclass
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
    def list_tables(self) -> list[TableMetadata]:
        raise NotImplementedError

    def profile_columns(self, schema_name: str, table_name: str, columns: list[str], row_count: int) -> dict[str, dict[str, Any]]:
        return {}
