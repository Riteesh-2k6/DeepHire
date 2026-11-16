"""Live transcription: the browser sends 16 kHz PCM chunks while you talk; each stretch of speech is
transcribed as soon as you pause, so captions appear live and the final transcript is ready moments
after you finish. Audio lives in memory only for the length of the answer."""
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import speech

RATE = 16000
FRAME = 480                 # 30 ms analysis frames
PAUSE_S = 0.5               # cut a segment at a pause at least this long...
MAX_SEGMENT_S = 12.0        # ...or at the quietest moment once this much unbroken speech has built up
MIN_SPEECH_S = 0.3          # a segment with less voiced audio than this is skipped (Whisper invents text in silence)

# One transcription at a time: they share the CPU with the grading model and the browser.
_worker = ThreadPoolExecutor(max_workers=1)
_streams = {}
_streams_lock = threading.Lock()


def frame_rms(audio):
    n = len(audio) // FRAME
    if not n:
        return np.zeros(0, np.float32)
    return np.sqrt((audio[: n * FRAME].reshape(n, FRAME) ** 2).mean(axis=1))


def silence_threshold(rms):
    """Quiet relative to this recording's own noise floor, with an absolute minimum."""
    return max(0.008, float(np.percentile(rms, 20)) * 2.5) if len(rms) else 0.008


def find_cut(rms, threshold, pause_frames, max_frames):
    """Frame index to cut the uncommitted audio at, or None to wait for more.

    Cuts in the middle of the last pause long enough to count; with no pause, cuts at the quietest
    frame of the last 2 s once the segment has grown past max_frames."""
    silent = rms < threshold
    k = len(silent) - 1
    while k >= 0:                       # walk runs of silence from the end
        if not silent[k]:
            k -= 1
            continue
        j = k
        while j >= 0 and silent[j]:
            j -= 1
        run_start, run_end = j + 1, k + 1
        if run_end - run_start >= pause_frames and run_start > 0:   # a real pause, after some speech
            return (run_start + run_end) // 2
        k = j
    if len(rms) > max_frames:
        window = rms[-int(2 / 0.03):]
        return len(rms) - len(window) + int(np.argmin(window))
    return None


class Stream:
    def __init__(self):
        self.audio = np.zeros(0, np.float32)
        self.committed = 0            # samples already transcribed
        self.words = []
        self.next_seq = 0
        self.gap = False              # a chunk was lost or reordered: the final pass uses the full recording
        self.lock = threading.Lock()
        self.busy = False             # a transcription pass is queued or running
        self.dirty = False            # audio arrived since that pass started

    def add(self, seq, pcm16):
        with self.lock:
            if seq != self.next_seq:
                self.gap = True
            self.next_seq = seq + 1
            chunk = np.frombuffer(pcm16, "<i2").astype(np.float32) / 32768.0
            self.audio = np.concatenate([self.audio, chunk])

    def _segment(self, final):
        with self.lock:
            tail = self.audio[self.committed:]
            start = self.committed
        rms = frame_rms(tail)
        if final:
            cut = len(tail)
        else:
            f = find_cut(rms, silence_threshold(frame_rms(self.audio)), int(PAUSE_S / 0.03), int(MAX_SEGMENT_S / 0.03))
            if f is None:
                return None
            cut = f * FRAME
        voiced = (rms[: cut // FRAME] >= silence_threshold(rms)).sum() * 0.03 if len(rms) else 0
        return start, tail[:cut], voiced

    def advance(self, final=False):
        """Transcribe every complete segment (and the tail, when final)."""
        while True:
            seg = self._segment(final)
            if not seg or not len(seg[1]):
                return
            start, audio, voiced = seg
            if voiced >= MIN_SPEECH_S:
                tail_text = " ".join(w["word"] for w in self.words[-30:])
                words = speech.transcribe_array(audio, offset_s=start / RATE, context=tail_text)
                with self.lock:
                    self.words.extend(words)
            with self.lock:
                self.committed = start + len(audio)
            if final:
                return

    def text(self):
        with self.lock:
            return " ".join(w["word"] for w in self.words)


def key(session_id, index, part):
    return f"{session_id}:{index}:{part}"


def add_chunk(k, seq, pcm16):
    """Append a chunk and schedule transcription; returns the live caption so far."""
    with _streams_lock:
        s = _streams.setdefault(k, Stream()) if seq == 0 else _streams.get(k)
        if s is None:            # chunks for an answer that already finished, or never started
            return None
        if seq == 0 and s.next_seq:  # a re-recorded answer starts over
            s = _streams[k] = Stream()
    s.add(seq, pcm16)
    with s.lock:
        s.dirty = True               # audio arrived; a pass already running will pick it up
        start_pass = not s.busy
        s.busy = True
    if start_pass:
        def run():
            while True:
                with s.lock:
                    if not s.dirty:
                        s.busy = False
                        return
                    s.dirty = False
                try:
                    s.advance()
                except Exception:    # the final pass, or the full-recording fallback, still produces a transcript
                    with s.lock:
                        s.gap = True
                        s.busy = s.dirty = False
                    return
        _worker.submit(run)
    with s.lock:
        return {"text": " ".join(w["word"] for w in s.words), "words": list(s.words)}


def finish(k):
    """The full transcript (text, words), or None if streaming can't be trusted for this answer."""
    with _streams_lock:
        s = _streams.pop(k, None)
    if s is None:
        return None
    _worker.submit(s.advance, True).result()   # queued behind any segment still in progress
    if s.gap:
        return None
    return " ".join(w["word"] for w in s.words), s.words


def discard(k):
    with _streams_lock:
        _streams.pop(k, None)
