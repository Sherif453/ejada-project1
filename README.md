# Data Extraction App

Local document extraction app with a React/Vite frontend and a simple FastAPI backend.

## Run PostgreSQL

If PostgreSQL server is not installed in WSL:

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo service postgresql start
```

Create a database named `financial_extractor` and a user/password matching:

```text
fte / fte
```

One local setup option:

```bash
sudo -u postgres psql
```

Then run:

```sql
CREATE USER fte WITH PASSWORD 'fte';
CREATE DATABASE financial_extractor OWNER fte;
\q
```

Default backend connection:

```text
postgresql://fte:fte@127.0.0.1:5432/financial_extractor
```

Override it with:

```bash
export FTE_DATABASE_URL="postgresql://user:password@127.0.0.1:5432/dbname"
```

## Run Backend

Standard backend install:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m ensurepip --upgrade
python -m pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend install with hybrid table extraction:

```bash
cd backend
source .venv/bin/activate
python -m pip install -e ".[extraction]"
```

Gemini Vision is used for scanned table pages:

```bash
export GEMINI_API_KEY="your_api_key_here"
```

Check:

```text
http://127.0.0.1:8000/health
```

## Run Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

The frontend calls `http://localhost:8000` unless `frontend/.env` sets:

```text
VITE_API_BASE=http://localhost:8000
```

## Backend API

- `POST /api/documents`: upload multipart field `file`.
- `GET /api/documents`: list documents.
- `GET /api/documents/{id}`: poll extraction result.
- `GET /api/documents/search?q=...`: search finished extracted text.
- `DELETE /api/documents/{id}`: delete a document and its stored upload.

## Extraction Handoff

The extraction pipeline is wired through:

```text
backend/app/extraction/pipeline.py
```

It runs the default hybrid financial-table extractor and returns the backend
dictionary contract:

```python
def extract_document(path: Path) -> dict:
    ...
```

Useful extraction environment variables:

```text
GEMINI_API_KEY=
FTE_GEMINI_MODEL=gemini-2.5-flash-lite
FTE_GEMINI_MEDIA_RESOLUTION=medium
FTE_GEMINI_MAX_OUTPUT_TOKENS=8192
FTE_ENABLE_NATIVE_TEXT_TABLES=true
FTE_ENABLE_SCANNED_EXTRACTION=true
FTE_SCANNED_REQUIRE_TABLE_LINES=true
FTE_SCANNED_RENDER_DPI=150
FTE_MAX_SCANNED_PAGES=
```

More detail is in `backend/app/extraction/README.md`.
