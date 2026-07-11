from copy import deepcopy

import pytest

from app.main import validate_extraction_result


VALID_RESULT = {
    "text": "Statement of Cash Flows",
    "page_count": 2,
    "confidence": 0.95,
    "tables": [
        {
            "table_index": 0,
            "page_number": 1,
            "title": "Cash flow",
            "row_count": 2,
            "column_count": 2,
            "confidence": 0.9,
            "bbox": [10, 20, 300, 400],
            "columns": ["Line item", "2024"],
            "rows": [
                ["Revenue", "100"],
                ["Income", "40"],
            ],
        }
    ],
}


def test_valid_result_is_accepted() -> None:
    result = deepcopy(VALID_RESULT)
    assert validate_extraction_result(result) == result


def test_rows_are_normalized_to_rectangular_strings() -> None:
    result = deepcopy(VALID_RESULT)
    result["tables"][0]["columns"] = ["Line item", "2024", "2023"]
    result["tables"][0]["rows"] = [["Revenue", 100], ["Income"]]

    normalized = validate_extraction_result(result)
    table = normalized["tables"][0]
    assert table["row_count"] == 2
    assert table["column_count"] == 3
    assert table["rows"] == [["Revenue", "100", ""], ["Income", "", ""]]


def test_missing_note_cells_are_reinserted_before_financial_amounts() -> None:
    result = deepcopy(VALID_RESULT)
    result["tables"][0]["columns"] = ["Line item", "Notes", "2024", "2023"]
    result["tables"][0]["rows"] = [
        ["Cash profit flows", "680,719,382", "436,996,562", ""],
        ["Defined benefit obligations", "16", "14,786,185", "14,164,932"],
        ["Financial assets", "27,28", "81,038,285", "74,793,037"],
        ["Expected credit losses", "3,416,079", "(390,305)", ""],
    ]

    normalized = validate_extraction_result(result)
    table = normalized["tables"][0]

    assert table["rows"] == [
        ["Cash profit flows", "", "680,719,382", "436,996,562"],
        ["Defined benefit obligations", "16", "14,786,185", "14,164,932"],
        ["Financial assets", "27,28", "81,038,285", "74,793,037"],
        ["Expected credit losses", "", "3,416,079", "(390,305)"],
    ]


def test_note_first_columns_are_repaired_when_description_header_is_missing() -> None:
    result = deepcopy(VALID_RESULT)
    result["tables"][0]["columns"] = ["Notes", "2024", "2023", ""]
    result["tables"][0]["rows"] = [
        ["Cash profit flows", "680,719,382", "436,996,562", ""],
        ["Defined benefit obligations", "16", "14,786,185", "14,164,932"],
        ["Expected credit losses", "3,416,079", "(390,305)", ""],
    ]

    normalized = validate_extraction_result(result)
    table = normalized["tables"][0]

    assert table["columns"] == ["", "Notes", "2024", "2023"]
    assert table["rows"] == [
        ["Cash profit flows", "", "680,719,382", "436,996,562"],
        ["Defined benefit obligations", "16", "14,786,185", "14,164,932"],
        ["Expected credit losses", "", "3,416,079", "(390,305)"],
    ]


def test_confidence_outside_zero_to_one_is_rejected() -> None:
    result = deepcopy(VALID_RESULT)
    result["confidence"] = 95

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        validate_extraction_result(result)
