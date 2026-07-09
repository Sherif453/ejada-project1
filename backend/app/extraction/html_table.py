from html.parser import HTMLParser
from typing import Any


class TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cells: list[dict[str, Any]] = []
        self.row_count = 0
        self.column_count = 0
        self._row = -1
        self._column = 0
        self._occupied: set[tuple[int, int]] = set()
        self._active_cell: dict[str, Any] | None = None
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row += 1
            self._column = 0
            self.row_count = max(self.row_count, self._row + 1)
            return

        if tag not in {"td", "th"} or self._row < 0:
            return

        attr_map = dict(attrs)
        row_span = _positive_int(attr_map.get("rowspan"), default=1)
        column_span = _positive_int(attr_map.get("colspan"), default=1)

        while (self._row, self._column) in self._occupied:
            self._column += 1

        row = self._row
        column = self._column
        for covered_row in range(row, row + row_span):
            for covered_column in range(column, column + column_span):
                self._occupied.add((covered_row, covered_column))

        self.row_count = max(self.row_count, row + row_span)
        self.column_count = max(self.column_count, column + column_span)
        self._column += column_span
        self._active_text = []
        self._active_cell = {
            "row": row,
            "column": column,
            "text": "",
            "row_span": row_span,
            "column_span": column_span,
            "is_header": tag == "th" or row == 0,
        }

    def handle_data(self, data: str) -> None:
        if self._active_cell is not None:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag not in {"td", "th"} or self._active_cell is None:
            return

        text = " ".join("".join(self._active_text).split())
        self._active_cell["text"] = text
        self.cells.append(self._active_cell)
        self._active_cell = None
        self._active_text = []


def parse_table_html(html: str) -> tuple[list[dict[str, Any]], int, int]:
    parser = TableHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.cells, parser.row_count, parser.column_count


def _positive_int(value: str | None, *, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default
