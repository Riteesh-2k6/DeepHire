"""Local speech-to-text with faster-whisper. Audio is decoded from memory, never saved."""
import io
import os
import re
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


# Whisper invents text in near-silence, usually stock video phrases. A segment it thinks is probably
# silence and is unsure about is dropped (the usual Whisper rule), and so are whole segments that are
# just one of these phrases.
HALLUCINATIONS = {"thanks for watching", "thank you for watching", "thank you", "thanks", "please subscribe",
                  "like and subscribe", "subscribe to my channel", "see you next time", "bye", "you"}


def keep_segment(text, no_speech_prob, avg_logprob):
    if no_speech_prob > 0.6 and avg_logprob < -1.0:
        return False
    return re.sub(r"[^a-z ]", "", text.lower()).strip() not in HALLUCINATIONS


def _words(segments, offset_s=0.0):
    return [{"word": w.word.strip(), "start": round(float(w.start) + offset_s, 2), "end": round(float(w.end) + offset_s, 2)}
            for s in segments if keep_segment(s.text, s.no_speech_prob, s.avg_logprob) for w in s.words]


def transcribe_array(audio, offset_s=0.0, context=""):
    """One stretch of 16 kHz float32 speech (live transcription). `context` is the text so far, which
    keeps names and terms consistent across stretches. Word times are shifted by offset_s."""
    prompt = (FILLER_PROMPT + " " + context).strip()[-800:]
    segments, _ = load().transcribe(audio, language="en", word_timestamps=True, vad_filter=True,
                                    initial_prompt=prompt, condition_on_previous_text=False)
    return _words(segments, offset_s)


def transcribe(audio_bytes):
    """Return (text, words) where words = [{"word", "start", "end"}]."""
    segments, _ = load().transcribe(
        io.BytesIO(audio_bytes), language="en", word_timestamps=True,
        vad_filter=True,  # skips silence, which is where Whisper invents text
        initial_prompt=FILLER_PROMPT)
    words = _words(segments)
    return " ".join(w["word"] for w in words), words
