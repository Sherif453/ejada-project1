from collections.abc import Iterable
from typing import Any

from .html_table import parse_table_html


def build_result_from_paddle_outputs(
    *,
    ocr_outputs: Iterable[Any],
    table_outputs: Iterable[Any],
) -> dict[str, Any]:
    ocr_pages = [_to_plain_output(output) for output in ocr_outputs]
    table_pages = [_to_plain_output(output) for output in table_outputs]

    text_items = _collect_ocr_texts(ocr_pages)
    tables = _collect_tables(table_pages)
    table_text_items = [
        str(cell or "")
        for table in tables
        for row in table.get("rows", [])
        for cell in row
        if cell
    ]

    all_text_items = [*text_items, *table_text_items]
    confidence_values = [
        *_collect_float_values(ocr_pages, "rec_scores"),
        *[
            float(table["confidence"])
            for table in tables
            if isinstance(table.get("confidence"), (int, float))
        ],
    ]

    return {
        "text": "\n".join(item for item in all_text_items if item),
        "page_count": _page_count([*ocr_pages, *table_pages]),
        "confidence": _average(confidence_values),
        "tables": tables,
    }


def _collect_ocr_texts(outputs: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for output in outputs:
        for value in _find_values(output, "rec_texts"):
            if isinstance(value, list):
                texts.extend(str(item) for item in value if str(item).strip())
    return texts


def _collect_tables(outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    per_page_counts: dict[int, int] = {}

    for output in outputs:
        page_number = _page_number(output)
        page_table_count = per_page_counts.get(page_number, 0)
        table_res_lists = list(_find_values(output, "table_res_list"))

        for table_res_list in table_res_lists:
            if not isinstance(table_res_list, list):
                continue
            for table_payload in table_res_list:
                if not isinstance(table_payload, dict):
                    continue
                table = _table_from_payload(
                    table_payload,
                    page_number=page_number,
                    table_index=page_table_count,
                )
                tables.append(table)
                page_table_count += 1

        per_page_counts[page_number] = page_table_count

    return tables


def _table_from_payload(
    table_payload: dict[str, Any],
    *,
    page_number: int,
    table_index: int,
) -> dict[str, Any]:
    html = str(table_payload.get("pred_html") or table_payload.get("html") or "")
    cells, row_count, column_count = parse_table_html(html)

    if not cells:
        texts = _extract_texts_from_table_payload(table_payload)
        rows = [[text] for text in texts]
        column_count = 1 if rows else 0
    else:
        rows = _rows_from_cells(cells, row_count=row_count, column_count=column_count)

    columns, body_rows = _split_columns_and_rows(rows)

    return {
        "table_index": table_index,
        "page_number": page_number,
        "title": "",
        "row_count": len(body_rows),
        "column_count": max(
            len(columns),
            max((len(row) for row in body_rows), default=0),
        ),
        "confidence": _table_confidence(table_payload),
        "bbox": _union_bbox(table_payload.get("cell_box_list")),
        "columns": columns,
        "rows": body_rows,
    }


def _rows_from_cells(
    cells: list[dict[str, Any]],
    *,
    row_count: int,
    column_count: int,
) -> list[list[str]]:
    rows = [["" for _column in range(column_count)] for _row in range(row_count)]
    for cell in cells:
        row = cell.get("row")
        column = cell.get("column")
        if not isinstance(row, int) or not isinstance(column, int):
            continue
        if row < 0 or column < 0 or row >= row_count or column >= column_count:
            continue
        rows[row][column] = str(cell.get("text") or "")
    return rows


def _split_columns_and_rows(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    if not rows:
        return [], []
    first_row = rows[0]
    if _looks_like_header(first_row):
        return first_row, rows[1:]
    return [], rows


def _looks_like_header(row: list[str]) -> bool:
    non_empty = [str(cell).strip() for cell in row if str(cell).strip()]
    if not non_empty:
        return False
    year_count = sum(bool(str(cell).isdigit() and len(str(cell)) == 4) for cell in non_empty)
    has_note = any(cell.lower() in {"note", "notes"} for cell in non_empty)
    return year_count >= 1 or has_note


def _extract_texts_from_table_payload(table_payload: dict[str, Any]) -> list[str]:
    table_ocr = table_payload.get("table_ocr_pred")
    if not isinstance(table_ocr, dict):
        return []
    texts = table_ocr.get("rec_texts")
    if not isinstance(texts, list):
        return []
    return [str(text) for text in texts if str(text).strip()]


def _table_confidence(table_payload: dict[str, Any]) -> float | None:
    for key in ("structure_score", "confidence", "score"):
        value = table_payload.get(key)
        if isinstance(value, (int, float)):
            return _clamp_confidence(float(value))

    table_ocr = table_payload.get("table_ocr_pred")
    if isinstance(table_ocr, dict):
        score = _average(
            value
            for value in _to_float_list(table_ocr.get("rec_scores"))
            if value is not None
        )
        if score is not None:
            return score

    return None


def _union_bbox(boxes: Any) -> list[float] | None:
    if not isinstance(boxes, list):
        return None

    xs: list[float] = []
    ys: list[float] = []
    for box in boxes:
        values = _to_float_list(box)
        if len(values) < 4:
            continue
        if len(values) == 4:
            x0, y0, x1, y1 = values
            xs.extend([x0, x1])
            ys.extend([y0, y1])
        else:
            xs.extend(values[0::2])
            ys.extend(values[1::2])

    if not xs or not ys:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def _page_count(outputs: list[dict[str, Any]]) -> int | None:
    page_numbers = [_page_number(output) for output in outputs if output]
    if not page_numbers:
        return None
    return max(page_numbers)


def _page_number(output: dict[str, Any]) -> int:
    for value in _find_values(output, "page_index"):
        if isinstance(value, int) and not isinstance(value, bool):
            return value + 1 if value >= 0 else 1
    return 1


def _find_values(value: Any, key: str) -> Iterable[Any]:
    if isinstance(value, dict):
        for current_key, current_value in value.items():
            if current_key == key:
                yield current_value
            yield from _find_values(current_value, key)
    elif isinstance(value, list):
        for item in value:
            yield from _find_values(item, key)


def _collect_float_values(outputs: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for output in outputs:
        for candidate in _find_values(output, key):
            values.extend(_to_float_list(candidate))
    return values


def _average(values: Iterable[float]) -> float | None:
    numeric = [value for value in values if 0 <= value <= 1]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def _clamp_confidence(value: float) -> float:
    return min(1.0, max(0.0, value))


def _to_float_list(value: Any) -> list[float]:
    value = _to_plain(value)
    if isinstance(value, (int, float)):
        return [float(value)]
    if not isinstance(value, list):
        return []
    floats: list[float] = []
    for item in value:
        if isinstance(item, (int, float)):
            floats.append(float(item))
    return floats


def _to_plain_output(output: Any) -> dict[str, Any]:
    if hasattr(output, "json"):
        output = getattr(output, "json")
    output = _to_plain(output)
    if isinstance(output, dict):
        result = output.get("res")
        if isinstance(result, dict):
            return result
        return output
    return {}


def _to_plain(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return _to_plain(value.tolist())
    if isinstance(value, dict):
        return {str(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_plain(item) for item in value]
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
