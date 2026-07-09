# Hybrid Financial Table Extraction Pipeline

## Goal

Read an uploaded PDF or image and return a clean Python dictionary containing
only detected financial tables plus searchable table text.

The extraction code must not access PostgreSQL, modify API routes, or generate
frontend HTML.

## Current Implementation

`pipeline.py` defaults to `HybridFinancialTableExtractor`, which uses:

- `pdfplumber` for native/text-based PDF financial tables.
- PyMuPDF to render scanned PDF pages only when OCR is needed.
- Gemini Vision for scanned-page financial tables when an API key is
  configured.
- PaddleOCR plus coordinate heuristics as the local scanned-page backup.

The old full Paddle OCR/table-recognition path remains available with:

```bash
export FTE_EXTRACTOR_MODE=paddle_full
```

The default hybrid path avoids Paddle table recognition because it is too heavy
for full reports on CPU.

## Install Extraction Dependencies

From `backend/`:

```bash
source .venv/bin/activate
python -m pip install -e ".[extraction]"
```

The `extraction` extra installs `pdfplumber`, PyMuPDF, `google-genai`,
`paddleocr`, `paddlepaddle`, and `paddlex[ocr]`.

Gemini scanned-page setup:

```bash
export GEMINI_API_KEY="your_api_key_here"
export FTE_SCANNED_ENGINE=auto
```

`FTE_SCANNED_ENGINE=auto` uses Gemini when `GEMINI_API_KEY` or
`GOOGLE_API_KEY` is set, otherwise it falls back to PaddleOCR. Use
`FTE_SCANNED_ENGINE=gemini` to force Gemini or `FTE_SCANNED_ENGINE=paddle` to
force local OCR.

Recommended local CPU setting:

```bash
export FTE_PADDLE_DEVICE=cpu
```

Paddle/PaddleX downloads official models on the first extraction run. If
Hugging Face is unavailable, Paddle docs support changing the model source:

```bash
export PADDLE_PDX_MODEL_SOURCE=bos
```

Synthetic smoke tests:

```bash
python scripts/smoke_extraction.py
python scripts/smoke_extraction.py --paddle-full
```

The default smoke test runs the hybrid extractor. `--paddle-full` runs the old
full Paddle table-recognition pipeline and may take several minutes or more on
CPU.

## Tuning

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
```

- `FTE_ENABLE_NATIVE_TEXT_TABLES=true` helps borderless native PDF tables, but
  is slower than line-only extraction.
- `FTE_SCANNED_ENGINE=auto` uses Gemini for scanned pages when an API key is
  available and PaddleOCR otherwise.
- `FTE_SCANNED_REQUIRE_TABLE_LINES=true` skips scanned pages unless they have
  table ruling lines or enough dense text layout to be worth visual extraction.
- `FTE_MAX_SCANNED_PAGES=3` is useful for demos when a fully scanned PDF would
  otherwise OCR too many pages.
- `FTE_GEMINI_MODEL=gemini-3.5-flash` controls the Gemini model.
- `FTE_PADDLE_RUNTIME=direct` uses the lighter direct PaddleOCR wrapper; set it
  to another value to use the older PaddleX OCR pipeline.
- `FTE_EXTRACTOR_MODE=paddle_full` should be used only for experiments, not the
  default local app path.

## Required Function Boundary

File:

```text
backend/app/extraction/pipeline.py
```

```python
from pathlib import Path
from typing import Any

def extract_document(path: Path) -> dict[str, Any]:
    ...
```

Supported files:

```text
.pdf  .png  .jpg  .jpeg  .tif  .tiff
```

Return the Python dictionary directly:

```python
return result
```

Do not return `json.dumps(result)`, a filename, a DataFrame, or a custom object.

The backend validates and stores the returned dictionary as PostgreSQL JSONB.

## Required Result Format

```python
{
    "text": "Complete searchable document text",
    "page_count": 52,
    "confidence": 0.94,
    "tables": [
        {
            "table_index": 0,
            "page_number": 11,
            "title": "Statement of Cash Flows",
            "row_count": 2,
            "column_count": 3,
            "confidence": 0.96,
            "bbox": [70, 120, 540, 700],
            "columns": ["Description", "2022", "2021"],
            "rows": [
                ["Profit before zakat", "264,613,601", "211,952,573"],
                [
                    "Net cash from operating activities",
                    "669,173,857",
                    "438,618,610",
                ],
            ],
        }
    ],
}
```

## Document Rules

- `text`: string; use `""` if unavailable.
- `page_count`: non-negative integer or `None`.
- `confidence`: `0.0–1.0` or `None`.
- `tables`: always a list; use `[]` if none are detected.

## Table Rules

Every table must include:

```text
table_index, page_number, title, row_count,
column_count, confidence, bbox, columns, rows
```

- `table_index` starts at `0`.
- `page_number` starts at `1`.
- Table indexes must be unique on each page.
- `title` must be a string; use `""` if unknown.
- `row_count` must match `len(rows)` after normalization.
- `column_count` must cover `columns` and every row.
- `confidence` must be `0.0–1.0` or `None`.
- `bbox` must be `[x0, y0, x1, y1]` or `None`.
- Use one coordinate system consistently.
- `columns` must be a list of strings. Use `[]` if no header was detected.
- `rows` must be a list of row lists.
- Each row should be rectangular after backend normalization.
- Preserve meaningful blank cells as `""`.

## Row Rules

- Use strings for every cell value.
- Preserve row order from the source statement.
- Preserve column order from left to right.
- Put detected column headers in `columns`.
- Put body rows only in `rows`.
- Do not include merged-cell metadata in the default contract.

Preserve financial formatting exactly:

```text
(1,250)  -1,250  12.5%  SAR 1,000  Note 14  —
```

Do not convert `—` to `0`. Do not remove negative signs or accounting
parentheses.

## Allowed Value Types

Use only:

```text
str, int, float, bool, None, list, dict
```

Do not return `Path`, DataFrame, NumPy objects, PIL images, datetime objects,
custom classes, or database connections.

Convert values first:

```python
float(numpy_value)
array.tolist()
str(path)
```

## Failure Handling

Raise an exception for real failures:

```python
raise RuntimeError("OCR failed while processing page 12")
```

The backend sets status to `failed` and stores the error.

Do not hide critical failures by returning an empty successful result.
`"tables": []` is valid only when extraction succeeded and no tables were found.

## Responsibilities

### Extraction Code

Responsible for:

- Reading the source file
- Extracting text
- Detecting tables
- Reconstructing table headers and rows
- Returning the required dictionary
- Adapting Paddle output to the backend contract

Not responsible for PostgreSQL, database credentials, API routes, status
updates, React, HTML, or CSS.

## Implementation Files

```text
pipeline.py        public backend entrypoint
hybrid_engine.py  default native/scanned financial table extractor
gemini_engine.py  Gemini Vision -> backend result dictionary
paddle_engine.py  optional full PaddleX runtime wrapper
adapter.py        Paddle JSON -> backend result dictionary
html_table.py     Paddle HTML table helper for optional full-Paddle mode
```

### Backend

Responsible for calling `extract_document(path)`, validating the dictionary,
storing it in `documents.result_json`, and updating status, counts, confidence,
and errors.

### Frontend

Responsible for reading `result.tables`, rendering `columns` and `rows` as HTML
tables, and displaying the source file beside the extracted result.

## Flow

```text
Upload file
-> save file
-> status = processing
-> call extract_document(path)
-> validate result
-> store result as JSONB
-> status = done
```

On failure:

```text
exception -> store error -> status = failed
```

## Acceptance Checklist

- Returns a Python dictionary, not a JSON string.
- All required fields exist.
- Page numbers start at `1`.
- Table indexes start at `0`.
- `row_count` matches `len(rows)`.
- `column_count` covers `columns` and every row.
- Financial formatting is preserved.
- All values are JSON-compatible.
- Real failures raise exceptions.
- No PostgreSQL or frontend code is added.
