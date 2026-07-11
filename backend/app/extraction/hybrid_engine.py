from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .gemini_engine import get_gemini_vision_extractor


logger = logging.getLogger(__name__)

FINANCIAL_KEYWORDS = (
    "assets",
    "liabilities",
    "equity",
    "revenue",
    "income",
    "profit",
    "loss",
    "cash flow",
    "cash flows",
    "statement of financial position",
    "statement of income",
    "statement of comprehensive income",
    "statement of cash flows",
    "balance sheet",
    "zakat",
    "shareholders",
    "operating activities",
    "investing activities",
    "financing activities",
)
FINANCIAL_LINE_ITEM_KEYWORDS = (
    "allowance",
    "assets",
    "balance",
    "capital",
    "cash",
    "deposit",
    "depreciation",
    "dividend",
    "equity",
    "expense",
    "fair value",
    "financing",
    "income",
    "investments",
    "liabilities",
    "loss",
    "profit",
    "reserve",
    "retained",
    "revenue",
    "sukuk",
    "total",
    "zakat",
)
DATE_HEADER_TERMS = {
    "as",
    "at",
    "beginning",
    "end",
    "ended",
    "for",
    "january",
    "december",
    "period",
    "year",
    "years",
}
MONTH_TERMS = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}
HEADER_LABELS = {"note", "notes"}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
NUMBER_RE = re.compile(r"^[({-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?[)}]?$")
YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
TOKEN_RE = re.compile(r"\S+")


@dataclass(frozen=True)
class PositionedToken:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    score: float | None

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass(frozen=True)
class PositionedRow:
    cells: list[str]
    tokens: list[PositionedToken]

    @property
    def top(self) -> float:
        return min(token.top for token in self.tokens)

    @property
    def bottom(self) -> float:
        return max(token.bottom for token in self.tokens)


class HybridFinancialTableExtractor:
    def __init__(
        self,
        *,
        native_text_min_chars: int,
        render_dpi: int,
        enable_scanned_extraction: bool,
        max_scanned_pages: int | None,
        enable_native_text_tables: bool,
        require_scanned_table_lines: bool,
    ) -> None:
        self.native_text_min_chars = native_text_min_chars
        self.render_dpi = render_dpi
        self.enable_scanned_extraction = enable_scanned_extraction
        self.max_scanned_pages = max_scanned_pages
        self.enable_native_text_tables = enable_native_text_tables
        self.require_scanned_table_lines = require_scanned_table_lines

    def extract(self, path: Path) -> dict[str, Any]:
        extension = path.suffix.lower()
        if extension == ".pdf":
            return self._extract_pdf(path)
        if extension in IMAGE_EXTENSIONS:
            return self._extract_image(path)
        raise ValueError(f"Unsupported extraction file type: {extension}")

    def _extract_pdf(self, path: Path) -> dict[str, Any]:
        try:
            import pdfplumber
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "pdfplumber is required for hybrid extraction. "
                "Install with: python -m pip install -e '.[extraction]'"
            ) from exc

        tables: list[dict[str, Any]] = []
        scanned_pages: list[int] = []
        page_count = 0

        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            for page_index, page in enumerate(pdf.pages, start=1):
                text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                words = _filter_layout_noise_words(
                    page.extract_words(keep_blank_chars=False),
                    page_width=float(getattr(page, "width", 0) or 0),
                    page_height=float(getattr(page, "height", 0) or 0),
                )
                image_count = len(getattr(page, "images", []) or [])

                if _is_native_page(text, self.native_text_min_chars):
                    if _is_financial_table_page(text, words):
                        tables.extend(
                            self._extract_native_tables(
                                page=page,
                                page_number=page_index,
                                first_table_index=len(tables),
                                page_text=text,
                                page_words=words,
                            )
                        )
                elif image_count > 0:
                    scanned_pages.append(page_index)

        if self.enable_scanned_extraction and scanned_pages:
            if self.max_scanned_pages is not None:
                scanned_pages = scanned_pages[: self.max_scanned_pages]
            tables.extend(
                self._extract_scanned_pdf_tables(
                    path=path,
                    page_numbers=scanned_pages,
                    first_table_index=len(tables),
                )
            )

        return _result_from_tables(tables=tables, page_count=page_count)

    def _extract_image(self, path: Path) -> dict[str, Any]:
        try:
            tables = get_gemini_vision_extractor().extract_tables_from_image(
                path,
                page_number=1,
                first_table_index=0,
            )
        except Exception:
            mode = _gemini_on_error()
            logger.exception("Gemini image extraction failed; mode=%s", mode)
            if mode == "raise":
                raise
            tables = []
        return _result_from_tables(tables=tables, page_count=1)

    def _extract_native_tables(
        self,
        *,
        page: Any,
        page_number: int,
        first_table_index: int,
        page_text: str,
        page_words: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        word_tables: list[dict[str, Any]] = []
        for word_group in _native_word_groups(
            page_words,
            page_width=float(getattr(page, "width", 0) or 0),
            page_height=float(getattr(page, "height", 0) or 0),
        ):
            word_tables.extend(
                _tables_from_positioned_tokens(
                    tokens=_tokens_from_pdf_words(word_group),
                    page_number=page_number,
                    first_table_index=first_table_index + len(word_tables),
                    confidence=0.92,
                    method="native_word_coordinates",
                )
            )
        if word_tables:
            return word_tables

        tables: list[dict[str, Any]] = []
        seen: set[tuple[int, int, int, int]] = set()

        for settings_index, settings in enumerate(
            _native_table_settings(self.enable_native_text_tables)
        ):
            if settings_index > 0 and not _should_run_native_text_strategy(
                page_text,
                page_words,
            ):
                continue

            table_count_before = len(tables)
            try:
                found_tables = page.find_tables(table_settings=settings)
            except Exception:
                continue

            for found_table in found_tables:
                bbox = _bbox_to_list(getattr(found_table, "bbox", None))
                key = _bbox_key(bbox)
                if key in seen:
                    continue

                rows = _normalize_grid(found_table.extract())
                if not _is_valid_financial_table(rows):
                    continue

                seen.add(key)
                table = _table_from_grid(
                    rows=rows,
                    page_number=page_number,
                    table_index=first_table_index + len(tables),
                    bbox=bbox,
                    confidence=0.95,
                    title=_native_table_title(page, bbox),
                    method="native_pdf",
                )
                if not _table_has_usable_rows(table):
                    continue

                tables.append(table)

            if settings_index == 0 and len(tables) > table_count_before:
                break

        return tables

    def _extract_scanned_pdf_tables(
        self,
        *,
        path: Path,
        page_numbers: list[int],
        first_table_index: int,
    ) -> list[dict[str, Any]]:
        try:
            import fitz
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "PyMuPDF is required to render scanned PDF pages. "
                "Install with: python -m pip install -e '.[extraction]'"
            ) from exc

        tables: list[dict[str, Any]] = []
        zoom = self.render_dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with fitz.open(path) as document:
                for page_number in page_numbers:
                    page = document.load_page(page_number - 1)
                    image_path = temp_path / f"page-{page_number}.png"
                    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                    pixmap.save(image_path)

                    if (
                        self.require_scanned_table_lines
                        and not _image_has_table_lines(image_path)
                        and not _image_has_financial_statement_layout(image_path)
                    ):
                        continue

                    try:
                        tables.extend(
                            get_gemini_vision_extractor().extract_tables_from_image(
                                image_path,
                                page_number=page_number,
                                first_table_index=first_table_index + len(tables),
                            )
                        )
                    except Exception:
                        mode = _gemini_on_error()
                        logger.exception(
                            "Gemini scanned-page extraction failed on page %s; mode=%s",
                            page_number,
                            mode,
                        )
                        if mode == "raise":
                            raise

        return tables


@lru_cache(maxsize=1)
def get_hybrid_extractor() -> HybridFinancialTableExtractor:
    return HybridFinancialTableExtractor(
        native_text_min_chars=_int_env("FTE_NATIVE_TEXT_MIN_CHARS", 80),
        render_dpi=_int_env("FTE_SCANNED_RENDER_DPI", 110),
        enable_scanned_extraction=_bool_env("FTE_ENABLE_SCANNED_EXTRACTION", True),
        max_scanned_pages=_optional_int_env("FTE_MAX_SCANNED_PAGES"),
        enable_native_text_tables=_bool_env("FTE_ENABLE_NATIVE_TEXT_TABLES", True),
        require_scanned_table_lines=_bool_env(
            "FTE_SCANNED_REQUIRE_TABLE_LINES",
            True,
        ),
    )


def _gemini_on_error() -> str:
    value = os.getenv("FTE_GEMINI_ON_ERROR", "skip").strip().lower()
    if value in {"skip", "raise"}:
        return value
    return "skip"


def _is_native_page(text: str, min_chars: int) -> bool:
    return len("".join(text.split())) >= min_chars


def _is_financial_table_page(text: str, words: list[dict[str, Any]]) -> bool:
    lowered = text.lower()
    keyword_hit = any(keyword in lowered for keyword in FINANCIAL_KEYWORDS)
    table_signal = _word_table_signal(words)
    return table_signal and (keyword_hit or _strong_numeric_signal(words))


def _word_table_signal(words: list[dict[str, Any]]) -> bool:
    numeric_words = [
        word for word in words if _is_number_like(str(word.get("text") or ""))
    ]
    if len(numeric_words) < 6:
        return False

    numeric_columns: dict[int, int] = {}
    numeric_rows: dict[int, int] = {}
    for word in numeric_words:
        numeric_columns[round(float(word.get("x0", 0)) / 12)] = (
            numeric_columns.get(round(float(word.get("x0", 0)) / 12), 0) + 1
        )
        numeric_rows[round(float(word.get("top", 0)) / 8)] = (
            numeric_rows.get(round(float(word.get("top", 0)) / 8), 0) + 1
        )

    aligned_columns = sum(count >= 3 for count in numeric_columns.values())
    dense_rows = sum(count >= 2 for count in numeric_rows.values())
    return aligned_columns >= 2 or dense_rows >= 3


def _strong_numeric_signal(words: list[dict[str, Any]]) -> bool:
    numeric_words = [
        word for word in words if _is_number_like(str(word.get("text") or ""))
    ]
    if len(numeric_words) < 14:
        return False

    numeric_rows: dict[int, int] = {}
    for word in numeric_words:
        row_key = round(float(word.get("top", 0)) / 8)
        numeric_rows[row_key] = numeric_rows.get(row_key, 0) + 1
    return sum(count >= 2 for count in numeric_rows.values()) >= 5


def _should_run_native_text_strategy(
    text: str,
    words: list[dict[str, Any]],
) -> bool:
    lowered = text.lower()
    statement_hint = any(
        phrase in lowered
        for phrase in (
            "statement of financial position",
            "statement of income",
            "statement of comprehensive income",
            "statement of cash flows",
            "statement of changes in equity",
            "balance sheet",
        )
    )

    numeric_words = [
        word for word in words if _is_number_like(str(word.get("text") or ""))
    ]
    if len(numeric_words) < 10:
        return False

    numeric_rows: dict[int, int] = {}
    for word in numeric_words:
        row_key = round(float(word.get("top", 0)) / 8)
        numeric_rows[row_key] = numeric_rows.get(row_key, 0) + 1

    dense_rows = sum(count >= 2 for count in numeric_rows.values())
    return statement_hint or dense_rows >= 8


def _native_table_settings(enable_text_strategy: bool) -> list[dict[str, Any]]:
    settings = [
        {
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "snap_tolerance": 3,
            "join_tolerance": 3,
            "intersection_tolerance": 5,
            "edge_min_length": 8,
        }
    ]
    if enable_text_strategy:
        settings.append(
            {
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "snap_tolerance": 3,
                "join_tolerance": 3,
                "intersection_tolerance": 5,
                "min_words_vertical": 2,
                "min_words_horizontal": 1,
                "text_tolerance": 3,
            }
        )
    return settings


def _filter_layout_noise_words(
    words: list[dict[str, Any]],
    *,
    page_width: float,
    page_height: float,
) -> list[dict[str, Any]]:
    if not words:
        return []

    top_header_limit = 45.0
    right_nav_limit = page_width - max(55.0, page_width * 0.03) if page_width else None
    cleaned: list[dict[str, Any]] = []
    for word in words:
        top = _float_or_none(word.get("top"))
        x0 = _float_or_none(word.get("x0"))
        if top is not None and top <= top_header_limit:
            continue
        if right_nav_limit is not None and x0 is not None and x0 >= right_nav_limit:
            continue
        cleaned.append(word)

    return cleaned


def _native_word_groups(
    words: list[dict[str, Any]],
    *,
    page_width: float,
    page_height: float,
) -> list[list[dict[str, Any]]]:
    if not words:
        return []

    if page_width > 0 and page_height > 0 and page_width >= page_height * 1.25:
        midpoint = page_width / 2
        left: list[dict[str, Any]] = []
        right: list[dict[str, Any]] = []
        for word in words:
            x0 = _float_or_none(word.get("x0"))
            x1 = _float_or_none(word.get("x1"))
            if x0 is None or x1 is None:
                continue
            center_x = (x0 + x1) / 2
            if center_x <= midpoint:
                left.append(word)
            else:
                right.append(word)

        groups = [group for group in (left, right) if len(group) >= 8]
        if groups:
            return groups

    return [words]


def _normalize_grid(raw_rows: Any) -> list[list[str]]:
    if not isinstance(raw_rows, list):
        return []

    rows = [
        [_clean_cell(cell) for cell in row]
        for row in raw_rows
        if isinstance(row, list)
    ]
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return []

    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]

    non_empty_columns = [
        column
        for column in range(width)
        if any(row[column].strip() for row in rows)
    ]
    if not non_empty_columns:
        return []

    return [[row[column] for column in non_empty_columns] for row in rows]


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split())


def _is_valid_financial_table(rows: list[list[str]]) -> bool:
    if len(rows) < 2:
        return False
    column_count = max((len(row) for row in rows), default=0)
    if column_count < 2:
        return False
    if column_count > 14:
        return False

    flat_text = " ".join(cell for row in rows for cell in row if cell)
    non_empty = [cell for row in rows for cell in row if cell.strip()]
    if len(non_empty) < 4:
        return False

    short_fragments = sum(
        len(cell.strip()) <= 2 and not _is_number_like(cell)
        for cell in non_empty
    )
    if short_fragments / len(non_empty) > 0.35:
        return False

    numeric_count = sum(_is_number_like(cell) for cell in non_empty)
    numeric_rows = sum(
        sum(_is_number_like(cell) for cell in row if cell.strip()) >= 2
        for row in rows
    )
    keyword_hit = any(keyword in flat_text.lower() for keyword in FINANCIAL_KEYWORDS)
    line_item_hit = any(
        keyword in flat_text.lower()
        for keyword in FINANCIAL_LINE_ITEM_KEYWORDS
    )
    year_count = sum(bool(YEAR_RE.match(cell.strip())) for cell in non_empty)
    if column_count >= 8 and numeric_rows < max(2, len(rows) // 5):
        return False

    return numeric_count >= 4 and (keyword_hit or line_item_hit or year_count >= 1)


def _table_from_grid(
    *,
    rows: list[list[str]],
    page_number: int,
    table_index: int,
    bbox: list[float] | None,
    confidence: float | None,
    title: str,
    method: str,
) -> dict[str, Any]:
    columns, body_rows, derived_title = _split_columns_and_rows(rows)
    if not title:
        title = derived_title

    body_rows = _align_body_rows_to_columns(columns, body_rows)
    column_count = max(
        len(columns),
        max((len(row) for row in body_rows), default=0),
    )
    columns = _pad_row(columns, column_count) if columns else []
    body_rows = [_pad_row(row, column_count) for row in body_rows]

    return {
        "table_index": table_index,
        "page_number": page_number,
        "title": title,
        "row_count": len(body_rows),
        "column_count": column_count,
        "confidence": confidence,
        "bbox": bbox,
        "columns": columns,
        "rows": body_rows,
        "extraction_method": method,
    }


def _align_body_rows_to_columns(
    columns: list[str],
    rows: list[list[str]],
) -> list[list[str]]:
    note_column_index = next(
        (
            index
            for index, column in enumerate(columns)
            if column.strip().lower() in HEADER_LABELS
        ),
        None,
    )
    if note_column_index is None or note_column_index == 0:
        return rows

    aligned_rows: list[list[str]] = []
    for row in rows:
        aligned = list(row)
        if (
            len(aligned) == len(columns)
            and note_column_index + 1 < len(aligned)
            and aligned[-1] == ""
            and _is_number_like(aligned[note_column_index])
            and not _looks_like_note_reference(aligned[note_column_index])
        ):
            aligned = (
                aligned[:note_column_index]
                + [""]
                + aligned[note_column_index:-1]
            )
        aligned_rows.append(aligned)
    return aligned_rows


def _looks_like_note_reference(value: str) -> bool:
    text = value.strip()
    if not text or "," in text or YEAR_RE.match(text):
        return False
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return False
    return len(text) <= 6


def _table_has_usable_rows(table: dict[str, Any]) -> bool:
    rows = table.get("rows")
    if not isinstance(rows, list) or not rows:
        return False

    values = [
        str(cell)
        for row in rows
        if isinstance(row, list)
        for cell in row
    ]
    if not values:
        return False

    non_empty = [value for value in values if value.strip()]
    empty_ratio = 1 - (len(non_empty) / len(values))
    if len(rows) == 1 and empty_ratio > 0.5:
        return False
    return empty_ratio <= 0.75


def _split_columns_and_rows(rows: list[list[str]]) -> tuple[list[str], list[list[str]], str]:
    if not rows:
        return [], [], ""

    column_index = _find_column_header_index(rows)
    if column_index is None or column_index >= len(rows) - 1:
        return [], rows, _title_from_leading_rows(rows[:1])

    title = _title_from_leading_rows(rows[:column_index])
    columns, header_end_index = _columns_from_header_rows(rows, column_index)
    body_rows = [
        row
        for row in rows[header_end_index + 1 :]
        if not _is_unit_row(row)
    ]
    return columns, body_rows, title


def _find_column_header_index(rows: list[list[str]]) -> int | None:
    for index, row in enumerate(rows[:8]):
        non_empty = [cell.strip() for cell in row if cell.strip()]
        if len(non_empty) < 2:
            continue

        year_cells = sum(bool(YEAR_RE.match(cell)) for cell in non_empty)
        has_note = any(cell.lower() in {"note", "notes"} for cell in non_empty)

        if _is_date_title_row(row):
            continue

        if has_note and (year_cells >= 1 or _nearby_year_header(rows, index)):
            return index
        if year_cells >= 2 and len(non_empty) <= 8:
            return index

    return None


def _columns_from_header_rows(
    rows: list[list[str]],
    column_index: int,
) -> tuple[list[str], int]:
    columns = rows[column_index]
    header_end_index = column_index
    non_empty = [cell.strip() for cell in columns if cell.strip()]
    year_cells = [cell for cell in non_empty if YEAR_RE.match(cell)]
    has_note = any(cell.lower() in HEADER_LABELS for cell in non_empty)

    if has_note and len(year_cells) < 2 and column_index + 1 < len(rows):
        next_non_empty = [
            cell.strip()
            for cell in rows[column_index + 1]
            if cell.strip()
        ]
        next_years = [cell for cell in next_non_empty if YEAR_RE.match(cell)]
        if len(next_years) >= 2:
            columns = ["", non_empty[0], *next_years[:2]]
            header_end_index = column_index + 1
            return columns, header_end_index

    if not has_note and len(year_cells) >= 2:
        note_index = _adjacent_note_header_index(rows, column_index)
        if note_index is not None:
            columns = ["", "Note", *year_cells[:2]]
            header_end_index = max(column_index, note_index)
            return columns, header_end_index

    return columns, header_end_index


def _nearby_year_header(rows: list[list[str]], index: int) -> bool:
    for nearby_index in (index - 1, index + 1):
        if nearby_index < 0 or nearby_index >= len(rows):
            continue
        if _is_date_title_row(rows[nearby_index]):
            continue
        non_empty = [cell.strip() for cell in rows[nearby_index] if cell.strip()]
        if sum(bool(YEAR_RE.match(cell)) for cell in non_empty) >= 2:
            return True
    return False


def _adjacent_note_header_index(rows: list[list[str]], index: int) -> int | None:
    for nearby_index in (index - 1, index + 1):
        if nearby_index < 0 or nearby_index >= len(rows):
            continue
        non_empty = [
            cell.strip().lower()
            for cell in rows[nearby_index]
            if cell.strip()
        ]
        if non_empty and all(cell in HEADER_LABELS for cell in non_empty):
            return nearby_index
    return None


def _is_date_title_row(row: list[str]) -> bool:
    non_empty = [cell.strip().lower() for cell in row if cell.strip()]
    if not non_empty:
        return False
    year_cells = sum(bool(YEAR_RE.match(cell)) for cell in non_empty)
    if year_cells < 2:
        return False
    joined = " ".join(non_empty)
    return (
        "for the year" in joined
        or "years ended" in joined
        or "year ended" in joined
        or "december 31" in joined
        or "31 december" in joined
        or " and " in f" {joined} "
    )


def _is_unit_row(row: list[str]) -> bool:
    non_empty = [cell.strip().lower().replace(",", "") for cell in row if cell.strip()]
    if not non_empty:
        return False
    unit_values = {"000", "sr000", "sar000", "riyals", "sr'000", "sar'000"}
    return all(cell in unit_values for cell in non_empty)


def _title_from_leading_rows(rows: list[list[str]]) -> str:
    candidates: list[str] = []
    for row in rows:
        text = " ".join(cell for cell in row if cell).strip()
        if not text:
            continue
        numeric_cells = sum(_is_number_like(cell) for cell in row if cell)
        if numeric_cells <= 1:
            candidates.append(text)
    return " ".join(candidates[:2])


def _pad_row(row: list[str], width: int) -> list[str]:
    return row + [""] * max(0, width - len(row))


def _native_table_title(page: Any, bbox: list[float] | None) -> str:
    if bbox is None:
        return ""
    x0, top, x1, _bottom = bbox
    words = [
        word
        for word in page.extract_words(keep_blank_chars=False)
        if top - 72 <= float(word.get("bottom", 0)) <= top
        and x0 - 20 <= float(word.get("x0", 0)) <= x1 + 20
    ]
    if not words:
        return ""

    lines: dict[int, list[str]] = {}
    for word in words:
        line_key = round(float(word.get("top", 0)) / 6)
        lines.setdefault(line_key, []).append(str(word.get("text") or ""))
    if not lines:
        return ""
    return " ".join(lines[max(lines)])


def _tables_from_positioned_tokens(
    *,
    tokens: list[PositionedToken],
    page_number: int,
    first_table_index: int,
    confidence: float | None,
    method: str,
) -> list[dict[str, Any]]:
    if not tokens:
        return []

    page_text = " ".join(token.text for token in tokens)
    token_words = [
        {"text": token.text, "x0": token.x0, "top": token.top}
        for token in tokens
    ]
    if not _is_financial_table_page(page_text, token_words):
        return []

    positioned_rows = [
        row
        for row in _positioned_rows(tokens)
        if _row_has_table_value(row.cells)
    ]
    tables: list[dict[str, Any]] = []
    for group in _group_positioned_rows(positioned_rows):
        rows = [row.cells for row in group]
        max_columns = max(len(row) for row in rows)
        rows = [row + [""] * (max_columns - len(row)) for row in rows]
        if not _is_valid_financial_table(rows):
            continue

        group_tokens = [
            token
            for row in group
            for token in row.tokens
        ]
        bbox = [
            min(token.x0 for token in group_tokens),
            min(token.top for token in group_tokens),
            max(token.x1 for token in group_tokens),
            max(token.bottom for token in group_tokens),
        ]
        table = _table_from_grid(
            rows=rows,
            page_number=page_number,
            table_index=first_table_index + len(tables),
            bbox=bbox,
            confidence=confidence,
            title=_positioned_table_title(rows),
            method=method,
        )
        if not _table_has_usable_rows(table):
            continue
        tables.append(table)
    return tables


def _positioned_rows(tokens: list[PositionedToken]) -> list[PositionedRow]:
    rows: list[PositionedRow] = []
    for token_row in _token_rows(tokens):
        cells = _parse_positioned_row(token_row)
        if cells:
            rows.append(PositionedRow(cells=cells, tokens=token_row))
    return rows


def _group_positioned_rows(rows: list[PositionedRow]) -> list[list[PositionedRow]]:
    if not rows:
        return []

    ordered = sorted(rows, key=lambda row: row.top)
    heights = [
        max(1.0, row.bottom - row.top)
        for row in ordered
    ]
    median_height = sorted(heights)[len(heights) // 2]
    gap_limit = max(18.0, median_height * 3.5)

    groups: list[list[PositionedRow]] = []
    for row in ordered:
        if not groups:
            groups.append([row])
            continue

        previous = groups[-1][-1]
        if row.top - previous.bottom <= gap_limit:
            groups[-1].append(row)
        else:
            groups.append([row])

    return [group for group in groups if len(group) >= 2]


def _token_rows(tokens: list[PositionedToken]) -> list[list[PositionedToken]]:
    ordered = sorted(tokens, key=lambda token: (token.center_y, token.x0))
    heights = [max(1.0, token.bottom - token.top) for token in ordered]
    tolerance = max(8.0, sorted(heights)[len(heights) // 2] * 0.75) if heights else 8.0

    rows: list[list[PositionedToken]] = []
    for token in ordered:
        for row in rows:
            row_center = sum(item.center_y for item in row) / len(row)
            if abs(token.center_y - row_center) <= tolerance:
                row.append(token)
                break
        else:
            rows.append([token])

    return [sorted(row, key=lambda token: token.x0) for row in rows]


def _parse_positioned_row(tokens: list[PositionedToken]) -> list[str]:
    pieces: list[str] = []
    for token in tokens:
        pieces.extend(_split_token_text(token.text))
    if not pieces:
        return []

    first_value_index = next(
        (
            index
            for index, piece in enumerate(pieces)
            if _is_row_value_token(pieces, index)
        ),
        None,
    )
    if first_value_index is None:
        return [" ".join(pieces)]

    label = " ".join(pieces[:first_value_index]).strip()
    values = pieces[first_value_index:]
    if label:
        return [label, *values]
    return values


def _is_row_value_token(pieces: list[str], index: int) -> bool:
    piece = pieces[index]
    if not _is_number_like(piece):
        return False

    lowered_window = {
        part.strip(" ,.;:()").lower()
        for part in pieces[max(0, index - 4) : min(len(pieces), index + 5)]
    }
    leading_terms = {
        part.strip(" ,.;:()").lower()
        for part in pieces[: min(len(pieces), 8)]
    }
    normalized = piece.strip().replace(",", "")

    if lowered_window & MONTH_TERMS:
        if YEAR_RE.match(normalized) or normalized in {"1", "30", "31"}:
            return False

    if normalized in {"1", "30", "31"} and (
        lowered_window & DATE_HEADER_TERMS or leading_terms & DATE_HEADER_TERMS
    ):
        return False

    if YEAR_RE.match(piece.strip()) and index <= 6:
        if leading_terms & DATE_HEADER_TERMS:
            return False

    return True


def _split_token_text(text: str) -> list[str]:
    return [
        match.group(0).strip()
        for match in TOKEN_RE.finditer(text)
        if match.group(0).strip()
    ]


def _row_has_table_value(row: list[str]) -> bool:
    if not row:
        return False
    lowered_cells = [cell.strip().lower() for cell in row if cell.strip()]
    if lowered_cells and all(cell in HEADER_LABELS for cell in lowered_cells):
        return True
    numeric_cells = sum(_is_number_like(cell) for cell in row)
    if len(row) > 8 and numeric_cells / len(row) < 0.35:
        return False
    if numeric_cells >= 2:
        return True
    lowered = " ".join(row).lower()
    return any(keyword in lowered for keyword in FINANCIAL_KEYWORDS)


def _positioned_table_title(rows: list[list[str]]) -> str:
    for row in rows[:3]:
        text = " ".join(cell for cell in row if cell).strip()
        if text and any(keyword in text.lower() for keyword in FINANCIAL_KEYWORDS):
            return text
    return ""


def _tokens_from_pdf_words(words: list[dict[str, Any]]) -> list[PositionedToken]:
    tokens: list[PositionedToken] = []
    for word in words:
        text = str(word.get("text") or "").strip()
        if not text:
            continue

        x0 = _float_or_none(word.get("x0"))
        top = _float_or_none(word.get("top"))
        x1 = _float_or_none(word.get("x1"))
        bottom = _float_or_none(word.get("bottom"))
        if x0 is None or top is None or x1 is None or bottom is None:
            continue

        tokens.append(
            PositionedToken(
                text=text,
                x0=x0,
                top=top,
                x1=x1,
                bottom=bottom,
                score=None,
            )
        )
    return tokens


def _image_has_table_lines(path: Path) -> bool:
    try:
        import cv2
    except ModuleNotFoundError:
        return True

    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return True

    height, width = image.shape[:2]
    max_width = 1200
    if width > max_width:
        scale = max_width / width
        image = cv2.resize(image, (max_width, int(height * scale)))
        height, width = image.shape[:2]

    binary = cv2.adaptiveThreshold(
        image,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        15,
    )

    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(25, width // 25), 1),
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (1, max(25, height // 30)),
    )

    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)

    horizontal_lines = _count_line_contours(horizontal, horizontal=True)
    vertical_lines = _count_line_contours(vertical, horizontal=False)
    return horizontal_lines >= 3 and vertical_lines >= 2


def _image_has_financial_statement_layout(path: Path) -> bool:
    try:
        import cv2
    except ModuleNotFoundError:
        return True

    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return False

    height, width = image.shape[:2]
    max_width = 1000
    if width > max_width:
        scale = max_width / width
        image = cv2.resize(image, (max_width, int(height * scale)))
        height, width = image.shape[:2]

    blurred = cv2.GaussianBlur(image, (3, 3), 0)
    _, binary = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU,
    )
    dark_ratio = cv2.countNonZero(binary) / max(1, width * height)
    if dark_ratio < 0.006:
        return False

    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(18, width // 35), 2),
    )
    text_lines = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, horizontal_kernel)
    contours, _hierarchy = cv2.findContours(
        text_lines,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    content_boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, contour_width, contour_height = cv2.boundingRect(contour)
        if contour_width >= width * 0.04 and 4 <= contour_height <= height * 0.08:
            content_boxes.append((x, y, contour_width, contour_height))

    body_boxes = [
        box
        for box in content_boxes
        if height * 0.12 <= box[1] <= height * 0.82
    ]
    if len(body_boxes) < 10:
        return False

    narrow_boxes = [
        box
        for box in body_boxes
        if width * 0.08 <= box[2] <= width * 0.36
    ]
    wide_boxes = [
        box
        for box in body_boxes
        if box[2] >= width * 0.50
    ]
    x_bands = {
        round((x + contour_width / 2) / (width / 8))
        for x, _y, contour_width, _contour_height in narrow_boxes
    }

    return (
        len(narrow_boxes) >= 8
        and len(x_bands) >= 4
        and len(wide_boxes) <= max(4, len(body_boxes) // 3)
    )


def _count_line_contours(mask: Any, *, horizontal: bool) -> int:
    import cv2

    contours, _hierarchy = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    count = 0
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if horizontal and width >= 80 and width >= height * 8:
            count += 1
        elif not horizontal and height >= 60 and height >= width * 8:
            count += 1
    return count


def _result_from_tables(
    *,
    tables: list[dict[str, Any]],
    page_count: int | None,
) -> dict[str, Any]:
    tables = _sort_tables_for_output(tables)
    text = "\n".join(
        _table_to_text(table)
        for table in tables
        if table.get("rows")
    )
    confidence = _average(
        float(table["confidence"])
        for table in tables
        if isinstance(table.get("confidence"), (int, float))
    )
    return {
        "text": text,
        "page_count": page_count,
        "confidence": confidence,
        "tables": tables,
    }


def _average(values: Iterable[float]) -> float | None:
    numbers = [float(value) for value in values]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _sort_tables_for_output(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        enumerate(tables),
        key=lambda item: (
            _table_page_sort_key(item[1]),
            _table_index_sort_key(item[1]),
            item[0],
        ),
    )

    sorted_tables: list[dict[str, Any]] = []
    for output_index, (_original_index, table) in enumerate(ordered):
        sorted_table = dict(table)
        sorted_table["table_index"] = output_index
        sorted_tables.append(sorted_table)
    return sorted_tables


def _table_page_sort_key(table: dict[str, Any]) -> int:
    page_number = table.get("page_number")
    if isinstance(page_number, int) and not isinstance(page_number, bool):
        return page_number
    return 1_000_000


def _table_index_sort_key(table: dict[str, Any]) -> int:
    table_index = table.get("table_index")
    if isinstance(table_index, int) and not isinstance(table_index, bool):
        return table_index
    return 1_000_000


def _table_to_text(table: dict[str, Any]) -> str:
    rows: list[list[str]] = []
    columns = table.get("columns")
    if isinstance(columns, list) and any(columns):
        rows.append([str(cell or "") for cell in columns])
    for row in table.get("rows", []):
        if isinstance(row, list):
            rows.append([str(cell or "") for cell in row])
    return "\n".join(" | ".join(cell for cell in row if cell) for row in rows)


def _is_number_like(text: str) -> bool:
    value = text.strip().replace(" ", "")
    if not value:
        return False
    if YEAR_RE.match(value):
        return True
    return bool(NUMBER_RE.match(value))


def _bbox_to_list(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    floats = [_float_or_none(item) for item in value]
    if any(item is None for item in floats):
        return None
    return [float(item) for item in floats if item is not None]


def _bbox_key(bbox: list[float] | None) -> tuple[int, int, int, int]:
    if bbox is None:
        return (0, 0, 0, 0)
    return tuple(round(value) for value in bbox)  # type: ignore[return-value]


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _optional_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None
