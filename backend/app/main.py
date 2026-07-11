import json
import re
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


NOTE_HEADERS = {"note", "notes"}
YEAR_HEADER_RE = re.compile(r"^(?:19|20)\d{2}$")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="Simple Document Extraction API", lifespan=lifespan)

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

        columns = table.get("columns", [])
        if columns is None:
            columns = []
        if not isinstance(columns, list):
            raise ValueError(f"tables[{table_index}].columns must be a list")
        table["columns"] = [_cell_to_string(cell) for cell in columns]

        rows = table.get("rows")
        if not isinstance(rows, list):
            raise ValueError(f"tables[{table_index}].rows must be a list")

        normalized_rows: list[list[str]] = []
        for row_index, row in enumerate(rows):
            if not isinstance(row, list):
                raise ValueError(f"tables[{table_index}].rows[{row_index}] must be a list")
            normalized_rows.append([_cell_to_string(cell) for cell in row])
        table["rows"] = normalized_rows

        column_count = max(
            len(table["columns"]),
            max((len(row) for row in normalized_rows), default=0),
        )
        normalized_rows = [
            row + [""] * (column_count - len(row))
            for row in normalized_rows
        ]
        table["rows"] = normalized_rows
        if table["columns"]:
            table["columns"] = table["columns"] + [""] * (
                column_count - len(table["columns"])
            )

        table["columns"], normalized_rows = _repair_missing_note_cells(
            table["columns"],
            normalized_rows,
        )
        table["rows"] = normalized_rows
        table["row_count"] = len(normalized_rows)
        table["column_count"] = max(
            len(table["columns"]),
            max((len(row) for row in normalized_rows), default=0),
        )

    try:
        json.dumps(result)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Extraction result is not JSON-compatible: {exc}") from exc

    return result


def _cell_to_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _repair_missing_note_cells(
    columns: list[str],
    rows: list[list[str]],
) -> tuple[list[str], list[list[str]]]:
    """Restore blank Notes cells that some extractors omit in financial tables."""
    if not columns or not rows:
        return columns, rows

    width = max(len(columns), max((len(row) for row in rows), default=0))
    repaired_columns = _pad_cells(columns, width)
    repaired_rows = [_pad_cells(row, width) for row in rows]

    if (
        _is_note_header(repaired_columns[0])
        and _rows_look_like_description_first_statement(repaired_rows)
    ):
        if repaired_columns[-1].strip():
            repaired_columns = ["", *repaired_columns]
            repaired_rows = [[*row, ""] for row in repaired_rows]
        else:
            repaired_columns = ["", *repaired_columns[:-1]]

    note_column_index = next(
        (
            index
            for index, column in enumerate(repaired_columns)
            if _is_note_header(column)
        ),
        None,
    )
    if note_column_index is None or note_column_index + 1 >= len(repaired_columns):
        return repaired_columns, repaired_rows

    aligned_rows: list[list[str]] = []
    for row in repaired_rows:
        aligned = list(row)
        if (
            aligned[-1].strip() == ""
            and _looks_like_financial_amount(aligned[note_column_index])
            and not _looks_like_note_reference(aligned[note_column_index])
        ):
            aligned = (
                aligned[:note_column_index]
                + [""]
                + aligned[note_column_index:-1]
            )
        aligned_rows.append(aligned)

    return repaired_columns, aligned_rows


def _pad_cells(cells: list[str], width: int) -> list[str]:
    return [*cells, *([""] * (width - len(cells)))]


def _is_note_header(value: str) -> bool:
    return value.strip().lower() in NOTE_HEADERS


def _rows_look_like_description_first_statement(rows: list[list[str]]) -> bool:
    matching_rows = 0
    for row in rows[:20]:
        if len(row) < 3:
            continue
        first_cell = row[0].strip()
        if (
            not first_cell
            or _looks_like_financial_amount(first_cell)
            or _looks_like_note_reference(first_cell)
            or YEAR_HEADER_RE.match(first_cell)
        ):
            continue
        if any(_looks_like_financial_amount(cell) for cell in row[1:]):
            matching_rows += 1

    non_empty_rows = [
        row
        for row in rows
        if any(cell.strip() for cell in row)
    ]
    return matching_rows >= 2 or (matching_rows == 1 and len(non_empty_rows) <= 3)


def _looks_like_note_reference(value: str) -> bool:
    text = value.strip()
    if not text or YEAR_HEADER_RE.match(text):
        return False

    normalized = re.sub(r"\s+", "", text.lower())
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", normalized):
        return False

    return bool(
        re.fullmatch(
            r"\d{1,3}(?:(?:,|&|/|-|and)\d{1,3})*",
            normalized,
        )
    )


def _looks_like_financial_amount(value: str) -> bool:
    text = value.strip()
    if not text or YEAR_HEADER_RE.match(text) or _looks_like_note_reference(text):
        return False

    normalized = text.replace(" ", "").replace("\u2212", "-")
    is_parenthesized = normalized.startswith("(") and normalized.endswith(")")
    if is_parenthesized:
        normalized = normalized[1:-1]
    normalized = normalized.removeprefix("+").removeprefix("-")

    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?%?", normalized):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?%?", normalized):
        digits = re.sub(r"\D", "", normalized)
        return is_parenthesized or len(digits) >= 4
    return False


def run_extraction(document_id: str, path: Path) -> None:
    try:
        raw_result = extract_document(path)
        result = validate_extraction_result(raw_result)

        tables = result.get("tables", [])
        search_text = str(result.get("text") or "").strip()

        if not search_text:
            search_text = "\n".join(
                str(cell or "")
                for table in tables
                for row in table.get("rows", [])
                for cell in row
                if cell
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
