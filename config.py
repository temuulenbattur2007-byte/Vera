"""
config.py — Single configuration file for Vera.
Change settings here instead of hunting through multiple files.
"""
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
MODEL_DIR  = BASE_DIR / "model"
DOCS_DIR   = BASE_DIR / "documents"
LOGS_DIR   = BASE_DIR / "logs"
VOICES_DIR = BASE_DIR / "voices"
CHROMA_DIR = BASE_DIR / "chroma_db"

# ── User ──────────────────────────────────────────────────────────────────────
USER_NAME  = "TEK"
VERA_NAME  = "Vera"

# ── Model ─────────────────────────────────────────────────────────────────────
# Main text model (llama-cpp-python)
MODEL_PATH  = str(MODEL_DIR / "Qwen2.5-7B-Instruct-1M-Q6_K.gguf")
GPU_LAYERS  = 28       # Reduced from 40 to leave VRAM for vision model
CTX_SIZE    = 8192
TEMPERATURE = 0.7
MAX_TOKENS  = 800

# Vision model (transformers)
VL_MODEL_ID   = "Qwen/Qwen2.5-VL-3B-Instruct"
VL_MAX_TOKENS = 150
VL_MAX_IMAGE_SIZE = 1280  # px — only resize if larger

# ── Memory ────────────────────────────────────────────────────────────────────
SHORT_TERM_MESSAGES = 40   # max messages in context window
MEMORY_DAYS         = 7    # days of history to load on startup
RAG_RESULTS         = 4    # number of document chunks to retrieve

# ── Voice ─────────────────────────────────────────────────────────────────────
WHISPER_MODEL    = "base"   # tiny, base, small, medium
MIC_DEVICE       = None     # None = Windows default, or set device index
SAMPLE_RATE      = 16000
SILENCE_TIMEOUT  = 1.5      # seconds of silence before processing
ENERGY_THRESHOLD = 0.01

# TTS
VOICE_FILE = str(VOICES_DIR / "en_US-lessac-high.onnx")
TTS_ENABLED_DEFAULT = False  # False = off by default

# ── Web Search ────────────────────────────────────────────────────────────────
TAVILY_API_KEY = "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"

# ── UI ────────────────────────────────────────────────────────────────────────
WINDOW_SIZE  = "960x700"
WINDOW_TITLE = "Vera"

# ── Colors ────────────────────────────────────────────────────────────────────
BG         = "#0c0a0e"
BG_PANEL   = "#110f14"
BG_INPUT   = "#1a1520"
BG_USER    = "#1e1830"
GARNET     = "#8b1a2e"
GARNET_LT  = "#c42847"
GARNET_DIM = "#5a0f1d"
ROSE       = "#e8607a"
ROSE_LT    = "#f0909f"
WHITE      = "#f0eaf4"
MUTED      = "#6b5f75"
DIM        = "#3d3545"
GREEN      = "#6bcfa0"
RED        = "#ff5566"
AMBER      = "#f0a060"
BORDER     = "#221a2c"
BLUE       = "#6090e0"