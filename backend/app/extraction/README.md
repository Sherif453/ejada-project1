# Hybrid Financial Table Extraction Pipeline

## Goal

Read an uploaded PDF or image and return a clean Python dictionary containing
only detected financial tables plus searchable table text.

The extraction code must not access PostgreSQL, modify API routes, or generate
frontend HTML.

## Current Implementation

`pipeline.py` calls `HybridFinancialTableExtractor`, which uses:

- `pdfplumber` for native/text-based PDF financial tables.
- PyMuPDF to render scanned PDF pages and uploaded images.
- Gemini Vision for scanned-page and image financial tables.

There is no local scanned-table fallback in the current app. Scanned tables
require `GEMINI_API_KEY` or `GOOGLE_API_KEY`.

## Install Extraction Dependencies

From `backend/`:

```bash
source .venv/bin/activate
python -m pip install -e ".[extraction]"
```

The `extraction` extra installs `pdfplumber`, PyMuPDF, `google-genai`, and
OpenCV for lightweight scanned-page table/layout filtering.

Gemini setup:

```bash
export GEMINI_API_KEY="your_api_key_here"
export FTE_GEMINI_ON_ERROR=skip
```

`FTE_GEMINI_ON_ERROR=skip` prevents quota/rate-limit errors from failing the
whole upload; native PDF tables still extract, while unavailable scanned pages
are skipped. Use `FTE_GEMINI_ON_ERROR=raise` when debugging Gemini failures.

## Tuning

```text
GEMINI_API_KEY=
FTE_GEMINI_MODEL=gemini-2.5-flash-lite
FTE_GEMINI_FALLBACK_MODELS=gemini-3.5-flash,gemini-2.5-flash
FTE_GEMINI_MEDIA_RESOLUTION=medium
FTE_GEMINI_MAX_OUTPUT_TOKENS=8192
FTE_GEMINI_ON_ERROR=skip
FTE_ENABLE_NATIVE_TEXT_TABLES=true
FTE_ENABLE_SCANNED_EXTRACTION=true
FTE_SCANNED_REQUIRE_TABLE_LINES=true
FTE_SCANNED_RENDER_DPI=150
FTE_MAX_SCANNED_PAGES=
```

- `FTE_ENABLE_NATIVE_TEXT_TABLES=true` helps borderless native PDF tables, but
  is slower than line-only extraction.
- `FTE_SCANNED_REQUIRE_TABLE_LINES=true` skips scanned pages unless they have
  table ruling lines or a financial-statement-like multi-column layout.
- `FTE_MAX_SCANNED_PAGES=3` is useful for demos when a fully scanned PDF would
  otherwise call Gemini for too many pages.
- `FTE_GEMINI_MODEL=gemini-2.5-flash-lite` controls the first Gemini model to
  try.
- `FTE_GEMINI_FALLBACK_MODELS` controls retry models for temporary quota/high
  demand model errors.
- `FTE_GEMINI_MEDIA_RESOLUTION=medium` keeps scanned statement images readable.
- `FTE_GEMINI_MAX_OUTPUT_TOKENS=8192` caps scanned-page JSON output size.

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
                ["Net cash from operating activities", "669,173,857", "438,618,610"],
            ],
        }
    ],
}
```

## Document Rules

- `text`: string; use `""` if unavailable.
- `page_count`: non-negative integer or `None`.
- `confidence`: `0.0-1.0` or `None`.
- `tables`: always a list; use `[]` if none are detected.

## Table Rules

Every table must include:

```text
table_index, page_number, title, row_count,
column_count, confidence, bbox, columns, rows
```

- `table_index` starts at `0`.
- `page_number` starts at `1`.
- `title` must be a string; use `""` if unknown.
- `row_count` must match `len(rows)` after normalization.
- `column_count` must cover `columns` and every row.
- `confidence` must be `0.0-1.0` or `None`.
- `bbox` must be `[x0, y0, x1, y1]` or `None`.
- `columns` must be a list of strings. Use `[]` if no header was detected.
- `rows` must be a list of row lists.
- Preserve meaningful blank cells as `""`.

Preserve financial formatting exactly:

```text
(1,250)  -1,250  12.5%  SAR 1,000  Note 14
```

Do not convert blanks or dashes to `0`. Do not remove negative signs or
accounting parentheses.

## Failure Handling

Raise an exception for real failures:

```python
raise RuntimeError("Extraction failed while processing page 12")
```

The backend sets status to `failed` and stores the error.

Do not hide critical failures by returning an empty successful result.
`"tables": []` is valid only when extraction succeeded and no tables were found.

## Implementation Files

```text
pipeline.py        public backend entrypoint
hybrid_engine.py  default native/scanned financial table extractor
gemini_engine.py  Gemini Vision -> backend result dictionary
```
