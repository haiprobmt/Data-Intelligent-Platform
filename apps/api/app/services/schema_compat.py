from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

SQLITE_COLUMNS: dict[str, dict[str, str]] = {
    "metadata_tables": {
        "owner": "VARCHAR(180)",
        "steward": "VARCHAR(180)",
        "source_freshness_at": "DATETIME",
    },
    "documents": {
        "file_path": "VARCHAR(500)",
        "extracted_text": "TEXT",
        "extraction_metadata": "JSON",
    },
    "jobs": {
        "progress_percent": "INTEGER DEFAULT 0",
        "cancel_requested": "BOOLEAN DEFAULT 0",
    },
}


def ensure_schema_compat(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table_name, columns in SQLITE_COLUMNS.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, definition in columns.items():
                if column_name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))
