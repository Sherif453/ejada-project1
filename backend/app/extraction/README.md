# Extraction Handoff

## Goal

Implement one function that reads an uploaded PDF or image and returns a clean
Python dictionary containing searchable text and structured financial tables.

The extraction code must not access PostgreSQL, modify API routes, or generate
frontend HTML.

## Required Function

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
            "row_count": 3,
            "column_count": 3,
            "confidence": 0.96,
            "bbox": [70, 120, 540, 700],
            "cells": [
                {
                    "row": 0,
                    "column": 0,
                    "text": "Description",
                    "row_span": 1,
                    "column_span": 1,
                    "is_header": True,
                },
                {
                    "row": 0,
                    "column": 1,
                    "text": "2022",
                    "row_span": 1,
                    "column_span": 1,
                    "is_header": True,
                },
                {
                    "row": 0,
                    "column": 2,
                    "text": "2021",
                    "row_span": 1,
                    "column_span": 1,
                    "is_header": True,
                },
                {
                    "row": 1,
                    "column": 0,
                    "text": "Profit before zakat",
                    "row_span": 1,
                    "column_span": 1,
                    "is_header": False,
                },
                {
                    "row": 1,
                    "column": 1,
                    "text": "264,613,601",
                    "row_span": 1,
                    "column_span": 1,
                    "is_header": False,
                },
                {
                    "row": 1,
                    "column": 2,
                    "text": "211,952,573",
                    "row_span": 1,
                    "column_span": 1,
                    "is_header": False,
                },
                {
                    "row": 2,
                    "column": 0,
                    "text": "Net cash from operating activities",
                    "row_span": 1,
                    "column_span": 1,
                    "is_header": False,
                },
                {
                    "row": 2,
                    "column": 1,
                    "text": "669,173,857",
                    "row_span": 1,
                    "column_span": 1,
                    "is_header": False,
                },
                {
                    "row": 2,
                    "column": 2,
                    "text": "438,618,610",
                    "row_span": 1,
                    "column_span": 1,
                    "is_header": False,
                },
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
column_count, confidence, bbox, cells
```

- `table_index` starts at `0`.
- `page_number` starts at `1`.
- Table indexes must be unique on each page.
- `title` must be a string; use `""` if unknown.
- `row_count` and `column_count` must cover all cells.
- `confidence` must be `0.0–1.0` or `None`.
- `bbox` must be `[x0, y0, x1, y1]` or `None`.
- Use one coordinate system consistently.
- `cells` must always be a list.

## Cell Rules

Every cell must include:

```text
row, column, text, row_span, column_span, is_header
```

- `row` and `column` start at `0`.
- `text` must always be a string.
- `row_span` and `column_span` must be at least `1`.
- `is_header` must be `True` or `False`.
- Cells must not overlap.
- Do not add duplicate cells inside merged areas.
- Preserve meaningful blank cells.

Preserve financial formatting exactly:

```text
(1,250)  -1,250  12.5%  SAR 1,000  Note 14  —
```

Do not convert `—` to `0`. Do not remove negative signs or accounting
parentheses.

## Merged Cell Example

```python
{
    "row": 0,
    "column": 1,
    "text": "Year ended",
    "row_span": 1,
    "column_span": 2,
    "is_header": True,
}
```

This covers row `0`, columns `1` and `2`. Do not return another cell at row `0`,
column `2`.

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

### Extraction Engineer

Responsible for:

- Reading the source file
- Extracting text
- Detecting tables
- Reconstructing rows, columns, headers, and merged cells
- Returning the required dictionary

Not responsible for PostgreSQL, database credentials, API routes, status
updates, React, HTML, or CSS.

### Backend

Responsible for calling `extract_document(path)`, validating the dictionary,
storing it in `documents.result_json`, and updating status, counts, confidence,
and errors.

### Frontend

Responsible for reading `result.tables`, rebuilding HTML tables, applying spans,
and displaying the source file beside the extracted result.

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
- Table, row, and column indexes start at `0`.
- Row and column counts cover every cell.
- Merged cells do not overlap other cells.
- Financial formatting is preserved.
- All values are JSON-compatible.
- Real failures raise exceptions.
- No PostgreSQL or frontend code is added.
