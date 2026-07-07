# OCR Upload + Results Screen

A drop-in React screen for uploading documents, watching OCR progress, and
searching extracted text. Built to talk to a FastAPI backend + Postgres,
but has no backend-specific code baked in beyond the fetch calls in `api.js`.

## Files

- `OCRWorkbench.jsx` — the screen (upload dropzone, document queue, reader panel, search).
- `api.js` — the only file that talks to the network. Swap the base URL or endpoints here.
- `ocr-workbench.css` — plain CSS, no Tailwind/UI-library dependency, safe to drop into any React setup.

## Install

```bash
npm install react react-dom
```

No other runtime dependencies. Fonts (`IBM Plex Sans`, `IBM Plex Mono`) are referenced
by name — add the Google Fonts `<link>` tags or `@font-face` rules for them, or the
CSS will fall back to system fonts gracefully.

## Usage

```jsx
import OCRWorkbench from "./OCRWorkbench";

export default function App() {
  return <OCRWorkbench />;
}
```

Set the backend URL via env var before building:

```
# .env (Vite)
VITE_API_BASE=https://your-fastapi-host

# .env (CRA)
REACT_APP_API_BASE=https://your-fastapi-host
```

## Backend contract expected from FastAPI

Share this with your backend teammate — it's the exact shape the frontend expects.

| Method | Path | Purpose | Response |
|---|---|---|---|
| `POST` | `/api/documents` | Upload a file (`multipart/form-data`, field `file`) | `{ id, filename, status: "processing", uploaded_at }` |
| `GET` | `/api/documents` | List all documents, most recent first | `[{ id, filename, status, uploaded_at, page_count, confidence }]` |
| `GET` | `/api/documents/{id}` | Poll one document's OCR status/result | `{ id, filename, status, uploaded_at, page_count, confidence, text, error }` |
| `GET` | `/api/documents/search?q=` | Full-text search over OCR'd text | `[{ id, filename, snippet, score }]` |
| `DELETE` | `/api/documents/{id}` | Remove a document | `204 No Content` |

`status` is one of: `"processing"`, `"done"`, `"failed"`.

Suggested Postgres shape for the OCR side (for your backend teammate, not required by the frontend):

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
- CORS: make sure FastAPI allows your dev origin (`http://localhost:5173` for Vite,
  `http://localhost:3000` for CRA) via `CORSMiddleware`.
