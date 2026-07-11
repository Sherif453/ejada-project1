from pathlib import Path
from typing import Any

from .hybrid_engine import get_hybrid_extractor


def extract_document(path: Path) -> dict[str, Any]:
    """Run financial-table extraction for one uploaded file.

    The backend calls only this function. The implementation may use any
    internal extraction pipeline as long as it returns a JSON-compatible
    dictionary matching the extraction README contract.
    """
    return get_hybrid_extractor().extract(path)
