"""Local speech-to-text with faster-whisper. Audio is decoded from memory, never saved."""
import io
import os
from functools import lru_cache

# Whisper tends to drop disfluencies; a filler-heavy prompt keeps more of them.
FILLER_PROMPT = "Umm, let me think, uh, hmm. Okay, so, um, here's my answer."


@lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel  # slow import, load on first use
    return WhisperModel(os.getenv("WHISPER_MODEL", "base"), device="cpu", compute_type="int8")


def transcribe(audio_bytes):
    """Return (text, words) where words = [{"word", "start", "end"}]."""
    segments, _ = _model().transcribe(
        io.BytesIO(audio_bytes), language="en", word_timestamps=True,
        vad_filter=True,  # skips silence, which is where Whisper invents text
        initial_prompt=FILLER_PROMPT)
    words = [{"word": w.word.strip(), "start": round(float(w.start), 2), "end": round(float(w.end), 2)}
             for s in segments for w in s.words]
    return " ".join(w["word"] for w in words), words
