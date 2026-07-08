from pathlib import Path
from typing import Any


def extract_document(path: Path) -> dict[str, Any]:
    """Temporary integration result.

    The extraction engineer will replace the body of this function.
    The backend contract must remain unchanged.
    """

    return {
        "text": (
            "Statement of Cash Flows. "
            "Profit before zakat 264,613,601 211,952,573. "
            "Net cash from operating activities "
            "669,173,857 438,618,610."
        ),
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