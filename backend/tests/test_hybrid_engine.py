from app.extraction.hybrid_engine import (
    HybridFinancialTableExtractor,
    PositionedToken,
    _gemini_on_error,
    _image_has_financial_statement_layout,
    _normalize_grid,
    _result_from_tables,
    _table_from_grid,
    _tables_from_positioned_tokens,
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


def test_positioned_tokens_reconstruct_financial_table() -> None:
    tokens = [
        PositionedToken("Statement", 10, 10, 70, 25, 0.98),
        PositionedToken("of", 75, 10, 90, 25, 0.98),
        PositionedToken("Income", 95, 10, 145, 25, 0.98),
        PositionedToken("Item", 10, 45, 45, 60, 0.99),
        PositionedToken("2024", 180, 45, 220, 60, 0.99),
        PositionedToken("2023", 260, 45, 300, 60, 0.99),
        PositionedToken("Revenue", 10, 75, 80, 90, 0.99),
        PositionedToken("100", 180, 75, 215, 90, 0.99),
        PositionedToken("90", 260, 75, 285, 90, 0.99),
        PositionedToken("Income", 10, 105, 70, 120, 0.99),
        PositionedToken("40", 180, 105, 210, 120, 0.99),
        PositionedToken("30", 260, 105, 285, 120, 0.99),
    ]

    tables = _tables_from_positioned_tokens(
        tokens=tokens,
        page_number=1,
        first_table_index=0,
        confidence=0.99,
        method="native_word_coordinates",
    )

    assert len(tables) == 1
    assert tables[0]["row_count"] >= 2
    assert tables[0]["column_count"] == 3
    assert tables[0]["confidence"] == 0.99
    assert any(row[0] == "Revenue" for row in tables[0]["rows"])


def test_gemini_error_mode_defaults_to_skip(monkeypatch) -> None:
    monkeypatch.delenv("FTE_GEMINI_ON_ERROR", raising=False)
    assert _gemini_on_error() == "skip"

    monkeypatch.setenv("FTE_GEMINI_ON_ERROR", "raise")
    assert _gemini_on_error() == "raise"

    monkeypatch.setenv("FTE_GEMINI_ON_ERROR", "bad-value")
    assert _gemini_on_error() == "skip"


def test_image_gemini_quota_error_can_skip(monkeypatch, tmp_path) -> None:
    class FailingGeminiExtractor:
        def extract_tables_from_image(self, *_args, **_kwargs):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setenv("FTE_GEMINI_ON_ERROR", "skip")
    monkeypatch.setattr(
        "app.extraction.hybrid_engine.get_gemini_vision_extractor",
        lambda: FailingGeminiExtractor(),
    )

    image_path = tmp_path / "table.png"
    image_path.write_bytes(b"fake image bytes")
    extractor = HybridFinancialTableExtractor(
        native_text_min_chars=80,
        render_dpi=110,
        enable_scanned_extraction=True,
        max_scanned_pages=None,
        enable_native_text_tables=True,
        require_scanned_table_lines=True,
    )

    result = extractor._extract_image(image_path)

    assert result["page_count"] == 1
    assert result["tables"] == []


def test_scanned_statement_layout_rejects_prose_pages(tmp_path) -> None:
    cv2 = __import__("cv2")
    numpy = __import__("numpy")

    prose = numpy.full((700, 500), 255, dtype=numpy.uint8)
    for y in range(120, 430, 24):
        cv2.rectangle(prose, (70, y), (430, y + 8), 0, -1)
    prose_path = tmp_path / "prose.png"
    cv2.imwrite(str(prose_path), prose)

    statement = numpy.full((700, 500), 255, dtype=numpy.uint8)
    for y in range(120, 430, 24):
        cv2.rectangle(statement, (55, y), (165, y + 8), 0, -1)
        cv2.rectangle(statement, (230, y), (270, y + 8), 0, -1)
        cv2.rectangle(statement, (310, y), (365, y + 8), 0, -1)
        cv2.rectangle(statement, (405, y), (460, y + 8), 0, -1)
    statement_path = tmp_path / "statement.png"
    cv2.imwrite(str(statement_path), statement)

    assert _image_has_financial_statement_layout(prose_path) is False
    assert _image_has_financial_statement_layout(statement_path) is True


def test_result_tables_are_sorted_by_page_number() -> None:
    result = _result_from_tables(
        tables=[
            {
                "table_index": 10,
                "page_number": 11,
                "columns": ["Item", "2022"],
                "rows": [["Cash flow", "100"]],
                "confidence": 0.9,
            },
            {
                "table_index": 11,
                "page_number": 7,
                "columns": ["Item", "2022"],
                "rows": [["Revenue", "200"]],
                "confidence": 0.9,
            },
        ],
        page_count=52,
    )

    assert [table["page_number"] for table in result["tables"]] == [7, 11]
    assert [table["table_index"] for table in result["tables"]] == [0, 1]
