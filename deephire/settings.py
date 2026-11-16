"""App settings, edited on the Settings page and kept in <data folder>/settings.json.

Environment variables (.env) still work as the starting values for anything not saved yet.
"""
import json
import os
import threading

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("DEEPHIRE_DATA") or BASE_DIR   # the desktop app sets this to %LOCALAPPDATA%\DeepHire
PATH = os.path.join(DATA_DIR, "settings.json")

VOICES = {  # Kokoro voices offered in Settings (the model has more)
    "af_heart": "US English, female (warm)", "af_bella": "US English, female (bright)",
    "am_michael": "US English, male", "am_adam": "US English, male (deeper)",
    "bf_emma": "British English, female", "bm_george": "British English, male",
}
WHISPER_MODELS = ("tiny", "base", "small")
MODES = ("mock", "practice")
COUNTS = (3, 5, 10)

DEFAULTS = {
    # new sessions start with these; the Practice page can still change them per session
    "count": 5, "follow_ups": True, "interruptions": True, "mode": "mock",
    # the interviewer's voice
    "tts_voice": os.getenv("TTS_VOICE", "af_heart"), "tts_speed": float(os.getenv("TTS_SPEED", "1.0")),
    # models
    "llm_base_url": os.getenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1"),
    "llm_model": os.getenv("LLM_MODEL", "gpt-oss-20b"),
    "llm_api_key": os.getenv("LLM_API_KEY", ""),
    "vision_model": os.getenv("VISION_MODEL", "qwen2.5-vl-3b"),
    "whisper_model": os.getenv("WHISPER_MODEL", "base"),
}

_lock = threading.Lock()
_cache = None


def _load():
    global _cache
    if _cache is None:
        saved = {}
        try:
            with open(PATH, encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            pass
        _cache = {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}
    return _cache


def get(key):
    with _lock:
        return _load()[key]


def all_settings():
    with _lock:
        return dict(_load())


def validate(changes):
    """Clean values for the keys given, or raise ValueError naming the first bad one."""
    out = {}
    for key, value in changes.items():
        if key not in DEFAULTS:
            raise ValueError(f"Unknown setting: {key}")
        if key in ("follow_ups", "interruptions"):
            ok = isinstance(value, bool)
        elif key == "count":
            ok = value in COUNTS
        elif key == "mode":
            ok = value in MODES
        elif key == "tts_voice":
            ok = value in VOICES
        elif key == "tts_speed":
            ok = isinstance(value, (int, float)) and 0.7 <= value <= 1.3
            value = float(value) if ok else value
        elif key == "whisper_model":
            ok = value in WHISPER_MODELS
        elif key == "llm_base_url":
            ok = isinstance(value, str) and value.startswith(("http://", "https://")) and len(value) < 300
            value = value.rstrip("/") if ok else value
        else:  # model names and the optional key
            ok = isinstance(value, str) and len(value) < 300
            value = value.strip() if ok else value
        if not ok:
            raise ValueError(f"Bad value for {key}")
        out[key] = value
    return out


def update(changes):
    """Validate, save and return the new settings."""
    clean = validate(changes)
    with _lock:
        current = _load()
        current.update(clean)
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        os.replace(tmp, PATH)
        return dict(current)
