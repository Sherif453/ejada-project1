import json

from app.extraction.gemini_engine import (
    _normalize_gemini_table,
    _parse_json_response,
)


def test_parse_json_response_accepts_fenced_json() -> None:
    payload = _parse_json_response(
        "```json\n" + json.dumps({"tables": []}) + "\n```"
    )

    assert payload == {"tables": []}


def test_normalize_gemini_table_returns_backend_shape() -> None:
    table = _normalize_gemini_table(
        {
            "title": "Statement of Financial Position",
            "columns": ["Line item", "Note", "2024", "2023"],
            "rows": [
                ["Cash", "5", "100", "90"],
                ["Total assets", "", "100", "90"],
            ],
            "confidence": 0.93,
        },
        page_number=7,
        table_index=2,
    )

    assert table == {
        "table_index": 2,
        "page_number": 7,
        "title": "Statement of Financial Position",
        "row_count": 2,
        "column_count": 4,
        "confidence": 0.93,
        "bbox": None,
        "columns": ["Line item", "Note", "2024", "2023"],
        "rows": [
            ["Cash", "5", "100", "90"],
            ["Total assets", "", "100", "90"],
        ],
        "extraction_method": "gemini_vision",
    }


def test_normalize_gemini_table_repairs_note_first_statement_columns() -> None:
    table = _normalize_gemini_table(
        {
            "title": "Statement of Financial Position",
            "columns": ["Note", "2022 SR", "2021 SR", ""],
            "rows": [["Property and equipment", "13", "100", "90"]],
        },
        page_number=9,
        table_index=0,
    )

    assert table is not None
    assert table["columns"] == ["", "Note", "2022 SR", "2021 SR"]
    assert table["rows"] == [["Property and equipment", "13", "100", "90"]]
