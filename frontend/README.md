# Frontend — OCR Upload + Results Screen

React frontend for the OCR document management project. Built with Vite.
Talks to a FastAPI backend + Postgres, but has no backend-specific code
baked in beyond the fetch calls in `src/api.js`.

## Setup

Requires [Node.js](https://nodejs.org/) (v18+ recommended) and npm.

```bash
cd frontend
npm install
```

## Run locally

```bash
npm run dev
```

This starts the Vite dev server, printing a local URL:

```
Local:   http://localhost:5173/
```

Open that URL in your browser. On first load you'll see a
"Couldn't load documents: Failed to fetch" message — that's expected
until the FastAPI backend is running (see **Connecting to the backend** below).

## Build for production

```bash
npm run build
```

Output goes to `frontend/dist/`.

## Project structure

```
frontend/
├── index.html
├── package.json
├── vite.config.js
└── src/
    ├── main.jsx            # Vite/React entry point
    ├── App.jsx             # Renders OCRWorkbench
    ├── OCRWorkbench.jsx    # The upload + results screen
    ├── api.js              # All network calls to the FastAPI backend
    └── ocr-workbench.css   # Styles (plain CSS, no framework dependency)
```

## Connecting to the backend

By default the app calls `http://localhost:8000`. To point at a different
host, create a `.env` file inside `frontend/`:

```
VITE_API_BASE=http://localhost:8000
```

Then restart `npm run dev` (Vite only reads `.env` on startup).

Make sure the FastAPI server has CORS enabled for your dev origin, e.g. in
`backend/app/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Backend contract expected from FastAPI

Share this with the backend teammate — it's the exact shape the frontend expects.

| Method | Path | Purpose | Response |
|---|---|---|---|
| `POST` | `/api/documents` | Upload a file (`multipart/form-data`, field `file`) | `{ id, filename, status: "processing", uploaded_at }` |
| `GET` | `/api/documents` | List all documents, most recent first | `[{ id, filename, status, uploaded_at, page_count, confidence }]` |
| `GET` | `/api/documents/{id}` | Poll one document's OCR status/result | `{ id, filename, status, uploaded_at, page_count, confidence, text, error }` |
| `GET` | `/api/documents/search?q=` | Full-text search over OCR'd text | `[{ id, filename, snippet, score }]` |
| `DELETE` | `/api/documents/{id}` | Remove a document | `204 No Content` |

`status` is one of: `"processing"`, `"done"`, `"failed"`.

Suggested Postgres shape for the OCR side (for the backend teammate, not required by the frontend):

```sql
create table documents (
  id uuid primary key default gen_random_uuid(),
  filename text not null,
  status text not null default 'processing',
  uploaded_at timestamptz not null default now(),
  page_count int,
  confidence real,
  text text,
  error text
);
-- for search:
create index documents_text_search_idx on documents using gin (to_tsvector('english', text));
```

## Behavior notes

- The screen uploads immediately on file select/drop, then polls
  `GET /api/documents/{id}` every 2s while `status === "processing"`.
- Search filters the visible queue down to matches returned by the backend
  (frontend does not do its own text search — that's the backend's job,
  typically Postgres `tsvector`/`tsquery` or a search extension).
- Fonts referenced by name (`IBM Plex Sans`, `IBM Plex Mono`) fall back to
  system fonts gracefully if not loaded — add Google Fonts `<link>` tags
  in `index.html` if you want the exact typeface.
