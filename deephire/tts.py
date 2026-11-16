"""The interviewer's voice: Kokoro-82M, run locally on the CPU. Text in, WAV out; nothing leaves the machine."""
import io
import os
import re
import threading
import wave
from functools import lru_cache

import numpy as np

MODEL_DIR = os.getenv("KOKORO_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "kokoro"))
THREADS = int(os.getenv("TTS_THREADS", "4"))   # same reason as WHISPER_THREADS: don't fight other programs

_lock = threading.Lock()
_engine = None


def available():
    return all(os.path.exists(os.path.join(MODEL_DIR, f)) for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"))


def load():
    global _engine
    with _lock:
        if _engine is None:
            import onnxruntime as ort
            from kokoro_onnx import Kokoro
            options = ort.SessionOptions()
            options.intra_op_num_threads = THREADS
            # CPU only. DirectML (Windows GPU) fails on this model's ConvTranspose layer, and CUDA would need
            # ~1 GB of NVIDIA libraries. Questions are voiced ahead of time, so CPU speed mostly doesn't show.
            session = ort.InferenceSession(os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"), options,
                                           providers=["CPUExecutionProvider"])
            _engine = Kokoro.from_session(session, os.path.join(MODEL_DIR, "voices-v1.0.bin"))
        return _engine


LONG_PIECE_WORDS = 14  # longer sentences are also split at commas, so the first audio is ready sooner


def sentences(text):
    """Pieces to voice one at a time: the first plays while the next is generated.
    static/js/media.js sentences() must split the same way, or the room misses the cache."""
    text = re.sub(r"\s+", " ", text or "").strip()
    out = []
    for s in re.split(r"(?<=[.!?])\s+", text):
        if not s:
            continue
        if len(s.split(" ")) <= LONG_PIECE_WORDS:
            out.append(s)
            continue
        buf = []  # comma pieces, merged into chunks of 8+ words so the speech doesn't turn choppy
        for p in re.split(r"(?<=,)\s+", s):
            buf.append(p)
            if len(" ".join(buf).split(" ")) >= 8:
                out.append(" ".join(buf))
                buf = []
        if buf:
            out.append(" ".join(buf))
    return out or ([text] if text else [])


def to_wav(samples, rate):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def current_voice():
    import settings
    return settings.get("tts_voice"), settings.get("tts_speed")


@lru_cache(maxsize=256)  # questions are voiced ahead of time; the room then gets them instantly
def _speak(text, voice, speed):
    samples, rate = load().create(text, voice=voice, speed=speed, lang="en-us")
    return to_wav(samples, rate)


def speak(text, voice=None, speed=None):
    """WAV bytes for one sentence in the voice chosen in Settings (or the one given)."""
    v, s = current_voice()
    return _speak(text, voice or v, speed or s)
