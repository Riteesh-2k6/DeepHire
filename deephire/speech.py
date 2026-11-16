"""Local speech-to-text with faster-whisper. Audio is decoded from memory, never saved."""
import io
import os
import threading

# Whisper tends to drop disfluencies; a filler-heavy prompt keeps more of them.
FILLER_PROMPT = "Umm, let me think, uh, hmm. Okay, so, um, here's my answer."
MODEL_NAME = os.getenv("WHISPER_MODEL", "base")
# Calibration knob: CTranslate2 otherwise starts a thread per core, and when other programs hold some
# cores every sync point waits for the slowest thread: 13 s of speech took ~50 s on a busy laptop
# with the default and ~16 s with 4 threads (1.3 s when the machine is idle).
THREADS = int(os.getenv("WHISPER_THREADS", "4"))

_lock = threading.Lock()
_model = None


def load():
    """The model, loaded once. From the local cache only: no network call, not even a version check."""
    global _model
    with _lock:  # the warm-up thread and the first answer can arrive together
        if _model is None:
            from faster_whisper import WhisperModel  # slow import, load on first use
            try:
                _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8",
                                      cpu_threads=THREADS, local_files_only=True)
            except Exception as e:
                raise RuntimeError(f"Whisper model '{MODEL_NAME}' isn't downloaded yet: "
                                   "run python scripts/fetch_vendor.py once.") from e
        return _model


def transcribe(audio_bytes):
    """Return (text, words) where words = [{"word", "start", "end"}]."""
    segments, _ = load().transcribe(
        io.BytesIO(audio_bytes), language="en", word_timestamps=True,
        vad_filter=True,  # skips silence, which is where Whisper invents text
        initial_prompt=FILLER_PROMPT)
    words = [{"word": w.word.strip(), "start": round(float(w.start), 2), "end": round(float(w.end), 2)}
             for s in segments for w in s.words]
    return " ".join(w["word"] for w in words), words
