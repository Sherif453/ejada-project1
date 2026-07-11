from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


PROMPT = """
Extract financial statement tables from this page image.
Return compact JSON only:
{"tables":[{"title":"","columns":[""],"rows":[[""]]}]}
Treat borderless financial statements as tables when line-item labels align with
year/period numeric columns. This includes statement of profit or loss,
financial position, cash flows, changes in equity, and comprehensive income.
For a statement page, extract the main statement table even if there are no cell
borders. Keep all line items and totals between the statement title and the
signatures/attached-notes footer. Use the visible header row as columns.
Do not extract auditor report prose, signatures, stamps, contact details,
footers, or page numbers. Preserve numbers exactly, including commas,
parentheses, dashes, and percentages. If the page truly has no financial
statement table, return {"tables":[]}.
""".strip()

GEMINI_TABLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
                "required": ["title", "columns", "rows"],
            },
        },
    },
    "required": ["tables"],
}


class GeminiVisionExtractor:
    def __init__(self, *, api_key: str, model: str, timeout_seconds: float) -> None:
        try:
            from google import genai
            from google.genai import types
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "google-genai is required for Gemini scanned-page extraction. "
                "Install with: python -m pip install -e '.[extraction]'"
            ) from exc

        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout_seconds * 1000),
            ),
        )
        self.model = model
        self.timeout_seconds = timeout_seconds

    def extract_tables_from_image(
        self,
        image_path: Path,
        *,
        page_number: int,
        first_table_index: int,
    ) -> list[dict[str, Any]]:
        image_bytes = image_path.read_bytes()
        contents = [
            PROMPT,
            self._types.Part.from_bytes(
                data=image_bytes,
                mime_type=_mime_type(image_path),
                media_resolution=_media_resolution(self._types),
            ),
        ]
        config = self._types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=GEMINI_TABLE_SCHEMA,
            max_output_tokens=int(os.getenv("FTE_GEMINI_MAX_OUTPUT_TOKENS", "8192")),
        )

        last_error: Exception | None = None
        for model in _model_candidates(self.model):
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                break
            except Exception as exc:
                last_error = exc
                if _is_retryable_model_error(exc):
                    continue
                raise
        else:
            assert last_error is not None
            raise last_error

        payload = _response_payload(response)
        raw_tables = payload.get("tables")
        if not isinstance(raw_tables, list):
            return []

        tables: list[dict[str, Any]] = []
        for raw_table in raw_tables:
            table = _normalize_gemini_table(
                raw_table,
                page_number=page_number,
                table_index=first_table_index + len(tables),
            )
            if table is not None:
                tables.append(table)
        return tables


@lru_cache(maxsize=1)
def get_gemini_vision_extractor() -> GeminiVisionExtractor:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Gemini scanned-page extraction requires GEMINI_API_KEY. "
            "Set GEMINI_API_KEY or GOOGLE_API_KEY before processing scanned pages."
        )

    return GeminiVisionExtractor(
        api_key=api_key,
        model=os.getenv("FTE_GEMINI_MODEL", "gemini-2.5-flash-lite"),
        timeout_seconds=float(os.getenv("FTE_GEMINI_TIMEOUT", "120")),
    )


def _normalize_gemini_table(
    raw_table: Any,
    *,
    page_number: int,
    table_index: int,
) -> dict[str, Any] | None:
    if not isinstance(raw_table, dict):
        return None

    columns = _string_list(raw_table.get("columns"))
    rows = _row_list(raw_table.get("rows"))
    if not rows:
        return None

    width = max(len(columns), max((len(row) for row in rows), default=0))
    if width < 2:
        return None

    columns = _repair_statement_columns(columns, width)
    columns = _pad_row(columns, width) if columns else []
    rows = [_pad_row(row, width) for row in rows]
    confidence = _confidence(raw_table.get("confidence"))

    return {
        "table_index": table_index,
        "page_number": page_number,
        "title": str(raw_table.get("title") or ""),
        "row_count": len(rows),
        "column_count": width,
        "confidence": confidence,
        "bbox": None,
        "columns": columns,
        "rows": rows,
        "extraction_method": "gemini_vision",
    }


def _parse_json_response(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini returned invalid JSON for scanned-page tables") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Gemini returned a non-object JSON payload")
    return payload


def _response_payload(response: Any) -> dict[str, Any]:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, dict):
        return parsed
    if hasattr(parsed, "model_dump"):
        dumped = parsed.model_dump() # type: ignore
        if isinstance(dumped, dict):
            return dumped

    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return _parse_json_response(text)

    return {"tables": []}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item or "") for item in value]


def _row_list(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    rows: list[list[str]] = []
    for row in value:
        if not isinstance(row, list):
            continue
        cleaned = [str(item or "") for item in row]
        if any(cell.strip() for cell in cleaned):
            rows.append(cleaned)
    return rows


def _pad_row(row: list[str], width: int) -> list[str]:
    return row + [""] * max(0, width - len(row))


def _confidence(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return min(1.0, max(0.0, float(value)))
    return None


def _repair_statement_columns(columns: list[str], width: int) -> list[str]:
    if not columns:
        return []

    first = columns[0].strip().lower()
    if first in {"note", "notes"} and width >= 4:
        if len(columns) == width and not columns[-1].strip():
            return ["", *columns[:-1]]
        if len(columns) == width - 1:
            return ["", *columns]

    return columns


def _model_candidates(primary_model: str) -> list[str]:
    configured = [
        model.strip()
        for model in os.getenv(
            "FTE_GEMINI_FALLBACK_MODELS",
            "gemini-3.5-flash,gemini-2.5-flash",
        ).split(",")
        if model.strip()
    ]
    candidates = [primary_model, *configured]
    deduped: list[str] = []
    for model in candidates:
        if model not in deduped:
            deduped.append(model)
    return deduped


def _is_retryable_model_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "429" in text
        or "resource_exhausted" in text
        or "quota" in text
        or "503" in text
        or "unavailable" in text
        or "high demand" in text
        or "overloaded" in text
    )


def _mime_type(path: Path) -> str:
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        return "image/jpeg"
    return "image/png"


def _media_resolution(types: Any) -> Any:
    value = os.getenv("FTE_GEMINI_MEDIA_RESOLUTION", "low").strip().lower()
    levels = {
        "low": types.PartMediaResolutionLevel.MEDIA_RESOLUTION_LOW,
        "medium": types.PartMediaResolutionLevel.MEDIA_RESOLUTION_MEDIUM,
        "high": types.PartMediaResolutionLevel.MEDIA_RESOLUTION_HIGH,
    }
    return types.PartMediaResolution(
        level=levels.get(value, types.PartMediaResolutionLevel.MEDIA_RESOLUTION_LOW)
    )
