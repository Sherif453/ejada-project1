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


def test_confidence_outside_zero_to_one_is_rejected() -> None:
    result = deepcopy(VALID_RESULT)
    result["confidence"] = 95

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        validate_extraction_result(result)
