# Financial Table Extraction Platform — Codex Rules

## Mission

Build a maintainable, versioned, local-first application that extracts financial
tables from heterogeneous PDFs, preserves complete source provenance, supports
auditable review, and exports only approved immutable versions. NEVER DELETE
ANYRHING UNRELATED TO THE PROJECT AND TRY TO KEEP C DRIVE WITH MORE THAN 1GB
AVAILABLE ALWAYS and no deployment, reaad AGENTS.md and PROJECT.md before every
major step

## Autonomy and efficiency

- Work autonomously. Do not ask for routine permission, approval, or
  confirmation.
- Inspect the relevant repository files before planning or editing; do not
  repeatedly scan unrelated areas.
- Make reasonable, reversible decisions when details are minor or ambiguous and
  state the assumption in the final summary.
- Stop only when required information is unavailable, implementation is
  impossible, or requirements materially conflict.
- Keep plans and final responses concise. Do not repeat the prompt, dump large
  file contents, or use subagents unless they provide clear value.
- Prefer the smallest complete change. Do not perform unrelated cleanup, broad
  rewrites, speculative abstractions, or dependency upgrades.

## Evidence-first implementation

- Read relevant architecture documents, nearby code, manifests, lockfiles,
  migrations, contracts, configuration, and tests before changing behavior.
- Never invent files, commands, scripts, dependencies, APIs, routes, database
  fields, environment variables, model identifiers, thresholds, or framework
  behavior.
- For version-sensitive behavior, verify the pinned version using lockfiles,
  installed source/types, or current official documentation.
- If something cannot be verified, mark it as an assumption rather than
  presenting it as fact.
- Never claim success unless the stated checks actually ran and passed.

## Non-negotiable product constraints

- Local open-source OCR and computer-vision models are allowed.
- Never place real financial documents, OCR output, extracted values, private
  filenames, screenshots, or client data in web searches, external tools, logs,
  fixtures, or examples. Use synthetic or explicitly redacted fixtures.
- Runtime workers must not download models. Models must be prepared locally,
  pinned, and checksum-verified.
- Only accepted table-region content may be stored as searchable extracted
  content; non-table body text must not be persisted.
- Original documents and approved table versions are immutable. Reprocessing or
  correction creates new runs/versions.

## Approved architecture

- Frontend: React, TypeScript, Vite, PDF.js, React Konva, TanStack Query, custom
  CSS-grid editor.
- API: FastAPI and Pydantic. Keep handlers thin and short-running.
- Data: PostgreSQL, SQLAlchemy, Alembic. Use Python `Decimal` and PostgreSQL
  `NUMERIC` for financial values.
- Jobs: Celery and Redis. Keep CPU and vision queues separable; never run long
  OCR/extraction inline in FastAPI.
- PDF/digital: PyMuPDF primary; Camelot only for validated native-text table
  regions; pdfplumber only when justified.
- Scanned tables: OpenCV/Pillow, Paddle table pipeline, PP-DocLayout, PP-OCRv6
  primary, Tesseract TSV verification, Table Transformer fallback.
- Export: openpyxl, CSV, JSON from approved versions only.
- Deployment: Docker Compose, Nginx, local volumes, local model store.
- Package management: backend `pyproject.toml` + `uv.lock`; frontend
  `package.json` + `pnpm-lock.yaml`.

## Extraction and data invariants

- Route per logical page and, when needed, per table region. Never assume one
  extraction method for an entire document.
- Support native, raster, mixed, rotated, spread, wide, borderless,
  merged-header, and multi-page tables.
- Preserve reversible transforms among physical-page, logical-page, PDF, crop,
  rotation, and rendered-image coordinates.
- Normalize every engine into one authoritative table graph. Preserve raw engine
  payloads and competing candidates.
- Each table/cell must retain document, physical/logical page, source rectangle,
  run, attempt, engine, model/configuration, confidence, provenance, and
  version.
- Represent merged cells with explicit row/column spans.
- Preserve raw text before normalization. Keep blank, dash, zero, sign,
  parentheses, percentage, date, note reference, currency, unit, and multiplier
  semantics distinct.
- Deterministic financial checks produce evidence and warnings; they never
  silently rewrite recognized values or force a table to balance.
- Scoring and routing decisions must be explainable and configuration-versioned.

## Backend, database, and job rules

- Validate inputs, preserve authentication/authorization boundaries, return
  typed contracts, and use stable structured errors.
- Treat uploaded PDFs and engine output as untrusted input. Validate signatures,
  actual type, limits, encryption policy, filenames, and checksums.
- Schema changes require an Alembic migration, model/schema updates, tests, and
  rollback assessment. Never edit applied migration history.
- Do not hold database transactions open during rendering, OCR, or model
  inference.
- Celery tasks should be idempotent, retry-safe, observable, and safe under
  duplicate delivery.
- Retries must not duplicate originals, approvals, or exports, overwrite
  successful artifacts, or lose prior attempts.
- Do not log complete documents, tables, OCR text, secrets, or sensitive local
  paths.

## Frontend and review rules

- Follow existing component, state, styling, and accessibility patterns; do not
  invent design tokens or routes.
- Keep PDF overlays correct across crop, rotation, zoom, pan, device-pixel
  ratio, spread splitting, and responsive layout.
- Review edits are versioned and auditable. Use explicit conflict handling;
  never silently overwrite another review.
- Approved versions are visibly read-only and exports reference the exact
  approved version.

## Dependencies and scope

- Add a production dependency only when existing tools are insufficient. Verify
  compatibility, license, maintenance, offline/local operation, security, and
  image-size impact; update the correct lockfile.
- Do not change public contracts, schema semantics, approval immutability,
  provenance, security boundaries, global extraction thresholds, or benchmark
  baselines unless the task requires it and the impact is documented.
- Never weaken typing, tests, validation, security, provenance, or benchmark
  expectations to make a change pass.

## Verification workflow

1. Inspect `git status`, relevant code, contracts, migrations, and tests.
2. Identify the root cause or exact capability gap.
3. Implement the smallest coherent change using existing patterns.
4. Add/update tests for success, failures, boundaries, retries, concurrency, and
   data integrity as applicable.
5. Run repository-defined focused checks first, then broader checks justified by
   the change.
6. For extraction, OCR, preprocessing, routing, model, or threshold changes, run
   a comparable before/after golden benchmark. Do not re-baseline solely to hide
   a regression.
7. Inspect the final diff and `git status` for unrelated changes, private data,
   secrets, debug output, and dependency drift.

## Completion report

Report only:

- what changed and why;
- files changed;
- exact verification commands and actual results;
- API/schema/job/extraction/security/benchmark impact;
- assumptions, remaining risks, or checks not run.
