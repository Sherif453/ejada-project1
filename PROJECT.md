# Simple Document Extraction App

## Current Goal

Build a small local app where the React frontend can upload documents, show
processing status, display extracted text, search finished documents, and delete
documents.

The backend is tailored to the current frontend in `frontend/src/api.js`.

## Scope

In scope:

- FastAPI HTTP API.
- PostgreSQL document metadata and extracted text storage.
- Local upload storage.
- One extraction handoff function for the extraction engineer.
- Frontend/backend local development.

Out of scope for the current backend task:

- SQLAlchemy models.
- Alembic migrations.
- Custom Pydantic schema files.
- Celery, Redis, worker queues, and deployment.
- Multiple extraction engines or fallback orchestration.
- Review/approval/versioning/export flows.

## Stack

Frontend:

- React 18
- Vite
- Plain JavaScript and CSS
- API calls in `frontend/src/api.js`

Backend:

- FastAPI
- PostgreSQL
- Raw `psycopg`
- `python-multipart` for file uploads
- Uvicorn for local development

Extraction:

- The backend calls `backend/app/extraction/pipeline.py::extract_document`.
- The default extraction implementation is a hybrid financial-table pipeline:
  native PDF tables with `pdfplumber`, scanned-page rendering with PyMuPDF, and
  Gemini Vision for scanned pages that look table-like when a Gemini API key is
  configured.
- The API and database code should not be changed for extraction implementation unless
  the frontend contract changes.

## Frontend API Contract

The frontend expects `VITE_API_BASE` or `http://localhost:8000`.

### Upload

`POST /api/documents`

Multipart form field:

- `file`

Response:

```json
{
  "id": "uuid",
  "filename": "annual-report.pdf",
  "status": "processing",
  "uploaded_at": "2026-07-08T12:00:00+00:00",
  "page_count": null,
  "confidence": null
}
```

### List

`GET /api/documents`

Response:

```json
[
  {
    "id": "uuid",
    "filename": "annual-report.pdf",
    "status": "done",
    "uploaded_at": "2026-07-08T12:00:00+00:00",
    "page_count": 12,
    "confidence": 0.94
  }
]
```

### Poll Result

`GET /api/documents/{id}`

Response:

```json
{
  "id": "uuid",
  "filename": "annual-report.pdf",
  "status": "done",
  "uploaded_at": "2026-07-08T12:00:00+00:00",
  "page_count": 12,
  "confidence": 0.94,
  "text": "extracted text",
  "error": null
}
```

### Search

`GET /api/documents/search?q=revenue`

Response:

```json
[
  {
    "id": "uuid",
    "filename": "annual-report.pdf",
    "snippet": "...revenue...",
    "score": 0.12
  }
]
```

### Delete

`DELETE /api/documents/{id}`

Response:

```text
204 No Content
```

## Status Values

- `processing`: upload is saved and extraction is running.
- `done`: extraction completed.
- `failed`: extraction raised an exception.

## Database

The backend creates the table on startup using raw SQL.

```sql
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
    ON documents USING gin (to_tsvector('english', coalesce(text, '')));
```

The same schema is in `backend/scripts/schema.sql`.

## Backend Flow

```text
Upload file
  -> validate extension and size
  -> insert documents row with status = processing
  -> save file under backend/data/uploads
  -> run extract_document(path) as a FastAPI background task
  -> update row to done or failed
```

## Extraction Function Contract

`backend/app/extraction/pipeline.py` must expose:

```python
def extract_document(path: Path) -> dict:
    ...
```

It must return:

```python
{
    "text": str,
    "page_count": int | None,
    "confidence": float | None,
    "tables": [
        {
            "table_index": int,
            "page_number": int,
            "title": str,
            "confidence": float | None,
            "bbox": list[float] | None,
            "columns": list[str],
            "rows": list[list[str]],
            "row_count": int,
            "column_count": int,
        }
    ],
}
```

The backend handles database updates. Extraction code should only read the file
and return extraction results or raise an exception.

Current extraction implementation:

- Page classification: native/scanned based on embedded text and image content.
- Native financial tables: `pdfplumber` table extraction.
- Scanned table pages: PyMuPDF render plus Gemini Vision JSON extraction when
  `GEMINI_API_KEY` or `GOOGLE_API_KEY` is set.
- Install with `python -m pip install -e ".[extraction]"` from `backend/`.
- Gemini Vision requires `GEMINI_API_KEY` or `GOOGLE_API_KEY` for scanned pages.

## Local Run

PostgreSQL must be running before the backend starts. The default connection is:

```text
postgresql://fte:fte@127.0.0.1:5432/financial_extractor
```

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m ensurepip --upgrade
python -m pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Extraction install:

```bash
cd backend
source .venv/bin/activate
python -m pip install -e ".[extraction]"
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

The backend health check is:

```text
http://localhost:8000/health
```
