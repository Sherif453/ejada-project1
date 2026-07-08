import os
from pathlib import Path


DATABASE_URL = os.getenv(
    "FTE_DATABASE_URL",
    "postgresql://fte:fte@127.0.0.1:5432/financial_extractor",
)
UPLOAD_DIR = Path(os.getenv("FTE_UPLOAD_DIR", "./data/uploads"))
MAX_UPLOAD_BYTES = int(os.getenv("FTE_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("FTE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]
