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
            "cells": [
                {
                    "row": 0,
                    "column": 0,
                    "text": "Heading",
                    "row_span": 1,
                    "column_span": 2,
                    "is_header": True,
                },
                {
                    "row": 1,
                    "column": 0,
                    "text": "Revenue",
                    "row_span": 1,
                    "column_span": 1,
                    "is_header": False,
                },
                {
                    "row": 1,
                    "column": 1,
                    "text": "100",
                    "row_span": 1,
                    "column_span": 1,
                    "is_header": False,
                },
            ],
        }
    ],
}


def test_valid_result_is_accepted() -> None:
    result = deepcopy(VALID_RESULT)
    assert validate_extraction_result(result) == result


def test_overlapping_cells_are_rejected() -> None:
    result = deepcopy(VALID_RESULT)
    result["tables"][0]["cells"].append(
        {
            "row": 0,
            "column": 1,
            "text": "Overlap",
            "row_span": 1,
            "column_span": 1,
            "is_header": True,
        }
    )

    with pytest.raises(ValueError, match="overlaps another cell"):
        validate_extraction_result(result)


def test_confidence_outside_zero_to_one_is_rejected() -> None:
    result = deepcopy(VALID_RESULT)
    result["confidence"] = 95

    with pytest.raises(ValueError, match="between 0 and 1"):
        validate_extraction_result(result)
