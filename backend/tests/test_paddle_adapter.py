from app.extraction.adapter import build_result_from_paddle_outputs
from app.extraction.html_table import parse_table_html


def test_parse_table_html_with_spans() -> None:
    html = """
    <html><body><table><tbody>
      <tr><td>Metric</td><td colspan="2">Year ended</td></tr>
      <tr><td>Revenue</td><td>100</td><td>90</td></tr>
    </tbody></table></body></html>
    """

    cells, row_count, column_count = parse_table_html(html)

    assert row_count == 2
    assert column_count == 3
    assert cells == [
        {
            "row": 0,
            "column": 0,
            "text": "Metric",
            "row_span": 1,
            "column_span": 1,
            "is_header": True,
        },
        {
            "row": 0,
            "column": 1,
            "text": "Year ended",
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
        {
            "row": 1,
            "column": 2,
            "text": "90",
            "row_span": 1,
            "column_span": 1,
            "is_header": False,
        },
    ]


def test_build_result_from_paddle_like_outputs() -> None:
    result = build_result_from_paddle_outputs(
        ocr_outputs=[
            {
                "res": {
                    "page_index": 0,
                    "rec_texts": ["Statement", "Revenue", "100"],
                    "rec_scores": [0.9, 0.8, 1.0],
                }
            }
        ],
        table_outputs=[
            {
                "res": {
                    "page_index": 0,
                    "table_res_list": [
                        {
                            "pred_html": (
                                "<table><tr><td>Line item</td><td>2024</td></tr>"
                                "<tr><td>Revenue</td><td>100</td></tr></table>"
                            ),
                            "cell_box_list": [
                                [10, 20, 110, 40],
                                [110, 20, 180, 40],
                                [10, 40, 110, 60],
                                [110, 40, 180, 60],
                            ],
                            "structure_score": 0.95,
                        }
                    ],
                }
            }
        ],
    )

    assert result["page_count"] == 1
    assert result["confidence"] is not None
    assert "Statement" in result["text"]
    assert "Revenue" in result["text"]
    assert result["tables"][0]["page_number"] == 1
    assert result["tables"][0]["row_count"] == 1
    assert result["tables"][0]["column_count"] == 2
    assert result["tables"][0]["bbox"] == [10, 20, 180, 60]
    assert result["tables"][0]["columns"] == ["Line item", "2024"]
    assert result["tables"][0]["rows"] == [["Revenue", "100"]]
