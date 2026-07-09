from pathlib import Path
from typing import Any

from .hybrid_engine import get_hybrid_extractor
from .paddle_engine import get_paddle_engine


def extract_document(path: Path) -> dict[str, Any]:
    """Run financial-table extraction for one uploaded file.

    The backend calls only this function. The implementation may use any
    internal extraction pipeline as long as it returns a JSON-compatible
    dictionary matching the extraction README contract.
    """
    if _extractor_mode() == "paddle_full":
        return get_paddle_engine().extract(path)
    return get_hybrid_extractor().extract(path)


def _extractor_mode() -> str:
    import os

    return os.getenv("FTE_EXTRACTOR_MODE", "hybrid").strip().lower()
