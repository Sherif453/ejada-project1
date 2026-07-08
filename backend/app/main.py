import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from psycopg.types.json import Jsonb

from .config import ALLOWED_EXTENSIONS, CORS_ORIGINS, MAX_UPLOAD_BYTES, UPLOAD_DIR
from .db import db_connection, init_db
from .extraction.pipeline import extract_document


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="Simple OCR Document API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/documents", status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    filename = Path(file.filename or "upload").name
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded file is too large")

    with db_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO documents (filename, content_type, storage_path, status)
            VALUES (%s, %s, '', 'processing')
            RETURNING id, filename, status, uploaded_at
            """,
            (filename, file.content_type),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=500, detail="Document insert failed")

        document_id = str(row["id"])
        storage_path = UPLOAD_DIR / f"{document_id}{extension}"
        storage_path.write_bytes(data)
        conn.execute(
            "UPDATE documents SET storage_path = %s WHERE id = %s",
            (str(storage_path), document_id),
        )
        conn.commit()

    background_tasks.add_task(run_extraction, document_id, storage_path)
    return _document_response(row)


@app.get("/api/documents")
def list_documents() -> list[dict[str, Any]]:
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                filename,
                status,
                uploaded_at,
                page_count,
                table_count,
                confidence
            FROM documents
            ORDER BY uploaded_at DESC
            """
        ).fetchall()
    return [_document_response(row) for row in rows]


@app.get("/api/documents/search")
def search_documents(q: str) -> list[dict[str, Any]]:
    query = q.strip()
    if not query:
        return []

    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                filename,
                ts_headline(
                    'english',
                    coalesce(text, ''),
                    plainto_tsquery('english', %s)
                ) AS snippet,
                ts_rank(
                    to_tsvector('english', coalesce(text, '')),
                    plainto_tsquery('english', %s)
                ) AS score
            FROM documents
            WHERE status = 'done'
              AND to_tsvector('english', coalesce(text, ''))
                  @@ plainto_tsquery('english', %s)
            ORDER BY score DESC, uploaded_at DESC
            LIMIT 50
            """,
            (query, query, query),
        ).fetchall()

    return [
        {
            "id": str(row["id"]),
            "filename": row["filename"],
            "snippet": row["snippet"] or "",
            "score": float(row["score"] or 0),
        }
        for row in rows
    ]


@app.get("/api/documents/{document_id}")
def get_document(document_id: UUID) -> dict[str, Any]:
    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT
                id,
                filename,
                content_type,
                storage_path,
                status,
                uploaded_at,
                page_count,
                table_count,
                confidence,
                text,
                result_json,
                error
            FROM documents
            WHERE id = %s
            """,
            (str(document_id),),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _document_response(row, include_result=True)


@app.get("/api/documents/{document_id}/source")
def get_document_source(document_id: UUID) -> FileResponse:
    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT filename, content_type, storage_path
            FROM documents
            WHERE id = %s
            """,
            (str(document_id),),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")

    path = Path(row["storage_path"])
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Stored source file not found")

    return FileResponse(
        path=path,
        media_type=row.get("content_type") or "application/pdf",
        filename=row["filename"],
        content_disposition_type="inline",
    )


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: UUID) -> Response:
    with db_connection() as conn:
        row = conn.execute(
            "DELETE FROM documents WHERE id = %s RETURNING storage_path",
            (str(document_id),),
        ).fetchone()
        conn.commit()

    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")

    storage_path = Path(row["storage_path"])
    if storage_path.exists() and storage_path.is_file():
        storage_path.unlink()
    return Response(status_code=204)


def validate_extraction_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("Extractor must return a JSON object")

    page_count = result.get("page_count")
    if page_count is not None:
        if not isinstance(page_count, int) or isinstance(page_count, bool) or page_count < 0:
            raise ValueError("result.page_count must be a non-negative integer")

    confidence = result.get("confidence")
    if confidence is not None:
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise ValueError("result.confidence must be a number or null")
        if confidence < 0 or confidence > 1:
            raise ValueError("result.confidence must be between 0.0 and 1.0")

    tables = result.get("tables", [])
    if not isinstance(tables, list):
        raise ValueError("result.tables must be a list")

    for table_index, table in enumerate(tables):
        if not isinstance(table, dict):
            raise ValueError(f"tables[{table_index}] must be an object")

        row_count = table.get("row_count")
        column_count = table.get("column_count")

        if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 0:
            raise ValueError(
                f"tables[{table_index}].row_count must be a non-negative integer"
            )

        if (
            not isinstance(column_count, int)
            or isinstance(column_count, bool)
            or column_count < 0
        ):
            raise ValueError(
                f"tables[{table_index}].column_count must be a non-negative integer"
            )

        cells = table.get("cells")
        if not isinstance(cells, list):
            raise ValueError(f"tables[{table_index}].cells must be a list")

        occupied_origins: set[tuple[int, int]] = set()

        for cell_index, cell in enumerate(cells):
            if not isinstance(cell, dict):
                raise ValueError(
                    f"tables[{table_index}].cells[{cell_index}] must be an object"
                )

            row = cell.get("row")
            column = cell.get("column")
            row_span = cell.get("row_span", 1)
            column_span = cell.get("column_span", 1)

            if not isinstance(row, int) or isinstance(row, bool) or row < 0:
                raise ValueError(f"Cell {cell_index} has an invalid row")

            if not isinstance(column, int) or isinstance(column, bool) or column < 0:
                raise ValueError(f"Cell {cell_index} has an invalid column")

            if (
                not isinstance(row_span, int)
                or isinstance(row_span, bool)
                or row_span < 1
            ):
                raise ValueError(f"Cell {cell_index} has an invalid row_span")

            if (
                not isinstance(column_span, int)
                or isinstance(column_span, bool)
                or column_span < 1
            ):
                raise ValueError(f"Cell {cell_index} has an invalid column_span")

            if row + row_span > row_count:
                raise ValueError(f"Cell {cell_index} extends beyond row_count")

            if column + column_span > column_count:
                raise ValueError(f"Cell {cell_index} extends beyond column_count")

            origin = (row, column)
            if origin in occupied_origins:
                raise ValueError(f"Duplicate cell at row {row}, column {column}")
            occupied_origins.add(origin)

            if not isinstance(cell.get("text", ""), str):
                raise ValueError(f"Cell {cell_index}.text must be a string")

    try:
        json.dumps(result)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Extraction result is not JSON-compatible: {exc}") from exc

    return result


def run_extraction(document_id: str, path: Path) -> None:
    try:
        raw_result = extract_document(path)
        result = validate_extraction_result(raw_result)

        tables = result.get("tables", [])
        search_text = str(result.get("text") or "").strip()

        if not search_text:
            search_text = "\n".join(
                str(cell.get("text") or "")
                for table in tables
                for cell in table.get("cells", [])
                if cell.get("text")
            )

        with db_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE documents
                SET
                    status = 'done',
                    text = %s,
                    page_count = %s,
                    table_count = %s,
                    confidence = %s,
                    result_json = %s,
                    error = NULL
                WHERE id = %s
                """,
                (
                    search_text,
                    result.get("page_count"),
                    len(tables),
                    result.get("confidence"),
                    Jsonb(result),
                    document_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError("Document was deleted before extraction completed")

            conn.commit()

    except Exception as exc:
        with db_connection() as conn:
            conn.execute(
                """
                UPDATE documents
                SET
                    status = 'failed',
                    error = %s
                WHERE id = %s
                """,
                (str(exc), document_id),
            )
            conn.commit()


def _document_response(
    row: dict[str, Any],
    *,
    include_result: bool = False,
) -> dict[str, Any]:
    payload = {
        "id": str(row["id"]),
        "filename": row["filename"],
        "status": row["status"],
        "uploaded_at": (
            row["uploaded_at"].isoformat() if row.get("uploaded_at") else None
        ),
        "page_count": row.get("page_count"),
        "table_count": row.get("table_count", 0),
        "confidence": row.get("confidence"),
    }

    if include_result:
        payload["text"] = row.get("text") or ""
        payload["result"] = row.get("result_json") or {
            "text": "",
            "page_count": row.get("page_count"),
            "confidence": row.get("confidence"),
            "tables": [],
        }
        payload["error"] = row.get("error")
        payload["source_url"] = f"/api/documents/{row['id']}/source"

    return payload
