from app.extraction.hybrid_engine import (
    OcrToken,
    _normalize_grid,
    _table_from_grid,
    _tables_from_ocr_tokens,
)


def test_native_grid_conversion_returns_backend_table_shape() -> None:
    rows = _normalize_grid(
        [
            ["Item", "2024", "2023"],
            ["Revenue", "100", "90"],
            ["", "", ""],
        ]
    )

    table = _table_from_grid(
        rows=rows,
        page_number=3,
        table_index=0,
        bbox=[10, 20, 200, 120],
        confidence=0.95,
        title="Statement of Income",
        method="native_pdf",
    )

    assert table["page_number"] == 3
    assert table["row_count"] == 1
    assert table["column_count"] == 3
    assert table["columns"] == ["Item", "2024", "2023"]
    assert table["rows"] == [["Revenue", "100", "90"]]
    assert table["extraction_method"] == "native_pdf"


def test_scanned_ocr_tokens_reconstruct_financial_table() -> None:
    tokens = [
        OcrToken("Statement", 10, 10, 70, 25, 0.98),
        OcrToken("of", 75, 10, 90, 25, 0.98),
        OcrToken("Income", 95, 10, 145, 25, 0.98),
        OcrToken("Item", 10, 45, 45, 60, 0.99),
        OcrToken("2024", 180, 45, 220, 60, 0.99),
        OcrToken("2023", 260, 45, 300, 60, 0.99),
        OcrToken("Revenue", 10, 75, 80, 90, 0.99),
        OcrToken("100", 180, 75, 215, 90, 0.99),
        OcrToken("90", 260, 75, 285, 90, 0.99),
        OcrToken("Income", 10, 105, 70, 120, 0.99),
        OcrToken("40", 180, 105, 210, 120, 0.99),
        OcrToken("30", 260, 105, 285, 120, 0.99),
    ]

    tables = _tables_from_ocr_tokens(
        tokens=tokens,
        page_number=1,
        first_table_index=0,
        confidence=0.99,
    )

    assert len(tables) == 1
    assert tables[0]["row_count"] >= 2
    assert tables[0]["column_count"] == 3
    assert tables[0]["confidence"] == 0.99
    assert any(row[0] == "Revenue" for row in tables[0]["rows"])
