from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, TypeAlias, cast

import psycopg
from psycopg.rows import DictRow, dict_row

from .config import DATABASE_URL


DbConnection: TypeAlias = psycopg.Connection[DictRow]


def connect() -> DbConnection:
    # Pyright/Pylance may infer the default TupleRow overload even though
    # dict_row is supplied. The cast only affects static typing.
    connection = psycopg.connect(
        DATABASE_URL,
        row_factory=cast(Any, dict_row),
    )
    return cast(DbConnection, connection)


@contextmanager
def db_connection() -> Iterator[DbConnection]:
    with connect() as conn:
        yield conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE EXTENSION IF NOT EXISTS pgcrypto;

            CREATE TABLE IF NOT EXISTS documents (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                filename text NOT NULL,
                content_type text,
                storage_path text NOT NULL,
                status text NOT NULL DEFAULT 'processing',
                uploaded_at timestamptz NOT NULL DEFAULT now(),

                page_count integer,
                table_count integer NOT NULL DEFAULT 0,
                confidence real,

                text text,
                result_json jsonb,
                error text
            );

            ALTER TABLE documents
                ADD COLUMN IF NOT EXISTS table_count integer
                NOT NULL DEFAULT 0;

            ALTER TABLE documents
                ADD COLUMN IF NOT EXISTS result_json jsonb;

            CREATE INDEX IF NOT EXISTS documents_uploaded_at_idx
                ON documents (uploaded_at DESC);

            CREATE INDEX IF NOT EXISTS documents_text_search_idx
                ON documents USING gin (
                    to_tsvector('english', coalesce(text, ''))
                );
            """
        )
        conn.commit()
