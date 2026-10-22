"""All settings come from environment variables. Nothing is hard-coded per machine."""
import os
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
PDF_DIR = DATA_DIR / "pdfs"
PAGE_IMG_DIR = DATA_DIR / "page_images"
DB_PATH = DATA_DIR / "index.sqlite3"
MODEL_DIR = DATA_DIR / "models"

DEMO_PDF_NAME = "velmora-annual-review-2025.pdf"
DEMO_GOLD_NAME = "velmora-annual-review-2025.gold.json"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:1.5b")
LLM_TIMEOUT = _int("LLM_TIMEOUT", 240)
LLM_CONTEXT_TOKENS = _int("LLM_CONTEXT_TOKENS", 4096)
VLM_MODEL = os.environ.get("VLM_MODEL", "").strip()

EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
RERANK_MODEL = os.environ.get("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")

# Keep the laptop responsive: ONNX models use only this many CPU threads.
MODEL_THREADS = _int("MODEL_THREADS", 2)
EMBED_BATCH = _int("EMBED_BATCH", 16)
# How long Ollama keeps the LLM in RAM after a question ("0" frees it at once).
LLM_KEEP_ALIVE = os.environ.get("LLM_KEEP_ALIVE", "2m")

# Public demo guards: keep the demo PDF safe and stop one visitor from filling the server.
PUBLIC_DEMO = os.environ.get("PUBLIC_DEMO", "0") == "1"
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 20)
MAX_UPLOAD_PAGES = _int("MAX_UPLOAD_PAGES", 80)
MAX_DOCS = _int("MAX_DOCS", 10)

TOP_K = _int("TOP_K", 6)
CANDIDATES = _int("CANDIDATES", 40)


def ensure_dirs() -> None:
    for d in (DATA_DIR, PDF_DIR, PAGE_IMG_DIR, MODEL_DIR):
        d.mkdir(parents=True, exist_ok=True)
