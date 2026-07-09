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

Standard backend install, without OCR model dependencies:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m ensurepip --upgrade
python -m pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend install with local hybrid table extraction:

```bash
cd backend
source .venv/bin/activate
python -m pip install -e ".[extraction]"
```

Gemini Vision is used for scanned table pages when an API key exists:

```bash
export GEMINI_API_KEY="your_api_key_here"
export FTE_SCANNED_ENGINE=auto
```

`FTE_SCANNED_ENGINE=auto` uses Gemini when `GEMINI_API_KEY` or
`GOOGLE_API_KEY` is set, otherwise it falls back to local PaddleOCR. To force a
specific scanned-page engine:

```bash
export FTE_SCANNED_ENGINE=gemini
export FTE_SCANNED_ENGINE=paddle
```

Paddle models are downloaded on first Paddle run. To use CPU explicitly:

```bash
export FTE_PADDLE_DEVICE=cpu
```

Synthetic extraction smoke checks:

```bash
python scripts/smoke_extraction.py
python scripts/smoke_extraction.py --paddle-full
```

The first command verifies the default hybrid path. The second command uses the
old full Paddle table-recognition mode; on CPU/WSL it can be very slow because
the full table model stack is loaded and run locally.

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
FTE_EXTRACTOR_MODE=hybrid
FTE_SCANNED_ENGINE=auto
GEMINI_API_KEY=
FTE_GEMINI_MODEL=gemini-3.5-flash
FTE_ENABLE_NATIVE_TEXT_TABLES=true
FTE_ENABLE_SCANNED_OCR=true
FTE_SCANNED_REQUIRE_TABLE_LINES=true
FTE_SCANNED_RENDER_DPI=110
FTE_MAX_SCANNED_PAGES=
FTE_PADDLE_DEVICE=cpu
FTE_PADDLE_RUNTIME=direct
FTE_PADDLE_USE_DOC_ORIENTATION=false
FTE_PADDLE_USE_DOC_UNWARPING=false
FTE_PADDLE_USE_TEXTLINE_ORIENTATION=false
```

More detail is in `backend/app/extraction/README.md`.
