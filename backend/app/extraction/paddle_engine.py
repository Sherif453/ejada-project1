import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .adapter import build_result_from_paddle_outputs


class PaddleRuntimeMissingError(RuntimeError):
    pass


class PaddleExtractionEngine:
    def __init__(
        self,
        *,
        device: str,
        ocr_pipeline_name: str,
        table_pipeline_name: str,
        enable_tables: bool,
    ) -> None:
        self.device = device
        self.ocr_pipeline_name = ocr_pipeline_name
        self.table_pipeline_name = table_pipeline_name
        self.enable_tables = enable_tables
        self._ocr_pipeline: Any | None = None
        self._table_pipeline: Any | None = None

    def extract(self, path: Path) -> dict[str, Any]:
        ocr_outputs = list(
            self._ocr_pipeline_instance().predict(
                input=str(path),
                use_doc_orientation_classify=_bool_env(
                    "FTE_PADDLE_USE_DOC_ORIENTATION",
                    False,
                ),
                use_doc_unwarping=_bool_env("FTE_PADDLE_USE_DOC_UNWARPING", False),
                use_textline_orientation=_bool_env(
                    "FTE_PADDLE_USE_TEXTLINE_ORIENTATION",
                    False,
                ),
            )
        )

        table_outputs: list[Any] = []
        if self.enable_tables:
            table_outputs = list(
                self._table_pipeline_instance().predict(
                    input=str(path),
                    use_doc_orientation_classify=_bool_env(
                        "FTE_PADDLE_USE_DOC_ORIENTATION",
                        False,
                    ),
                    use_doc_unwarping=_bool_env(
                        "FTE_PADDLE_USE_DOC_UNWARPING",
                        False,
                    ),
                    use_layout_detection=_bool_env(
                        "FTE_PADDLE_USE_LAYOUT_DETECTION",
                        True,
                    ),
                    use_ocr_results_with_table_cells=_bool_env(
                        "FTE_PADDLE_USE_OCR_WITH_TABLE_CELLS",
                        True,
                    ),
                )
            )

        return build_result_from_paddle_outputs(
            ocr_outputs=ocr_outputs,
            table_outputs=table_outputs,
        )

    def _ocr_pipeline_instance(self) -> Any:
        if self._ocr_pipeline is None:
            self._ocr_pipeline = self._create_pipeline(self.ocr_pipeline_name)
        return self._ocr_pipeline

    def _table_pipeline_instance(self) -> Any:
        if self._table_pipeline is None:
            self._table_pipeline = self._create_pipeline(self.table_pipeline_name)
        return self._table_pipeline

    def _create_pipeline(self, name: str) -> Any:
        try:
            from paddlex import create_pipeline
        except ModuleNotFoundError as exc:
            raise PaddleRuntimeMissingError(
                "Paddle extraction dependencies are not installed. "
                "Install them with: python -m pip install -e '.[extraction]'"
            ) from exc

        return create_pipeline(pipeline=name, device=self.device)


@lru_cache(maxsize=1)
def get_paddle_engine() -> PaddleExtractionEngine:
    return PaddleExtractionEngine(
        device=os.getenv("FTE_PADDLE_DEVICE", "cpu"),
        ocr_pipeline_name=os.getenv("FTE_PADDLE_OCR_PIPELINE", "OCR"),
        table_pipeline_name=os.getenv(
            "FTE_PADDLE_TABLE_PIPELINE",
            "table_recognition_v2",
        ),
        enable_tables=_bool_env("FTE_PADDLE_ENABLE_TABLES", True),
    )


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
