# Data Extraction App

Local OCR document app with a React/Vite frontend and a simple FastAPI backend.

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

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m ensurepip --upgrade
python -m pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
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
- `GET /api/documents/{id}`: poll OCR result.
- `GET /api/documents/search?q=...`: search finished OCR text.
- `DELETE /api/documents/{id}`: delete a document and its stored upload.

## Extraction Handoff

The extraction engineer only needs to implement:

```text
backend/app/extraction/pipeline.py
```

Function:

```python
def extract_document(path: Path) -> dict:
    return {
        "text": "...",
        "page_count": 1,
        "confidence": 0.95,
    }
```

More detail is in `backend/app/extraction/README.md`.
