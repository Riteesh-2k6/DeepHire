"""Delivery signals: observable facts about how an answer was spoken.

Pure functions over the word timestamps from the transcript and the face
counts the browser sends. Nothing here infers emotion or "confidence".
"""
import re

PAUSE_S = 2.0        # a gap between words at least this long counts as a pause
MIN_SPAN_S = 5.0     # shorter answers are too short for a meaningful pace
FILLERS = {"um", "umm", "uh", "uhh", "uhm", "er", "erm", "ah", "hmm", "hm", "mm"}

# Rules of thumb shown next to each number in the report, not grades.
RANGES = {
    "wpm": (120, 160),
    "fillers_per_min": (0, 3),
    "camera_pct": (60, 100),
}


def _norm(word):
    return re.sub(r"[^a-z']", "", word.lower())


# ---------- rambling: when the interviewer cuts in (observable signals only) ----------
# Calibration knobs. Speaking time counts from the first word to the latest one.
RAMBLE_SPEAKING_S = {"main": 120, "follow_up": 60}
REPEAT_MIN_S = 45          # don't judge repetition in short answers
REPEAT_RATIO = 0.35        # share of recent three-word phrases already said earlier in the answer
STOPWORDS = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "is", "it", "its", "that", "this", "so",
             "i", "you", "we", "be", "for", "with", "as", "at", "by", "then", "would", "will", "can", "just",
             "like", "basically", "actually", "okay", "yeah", "right", "do", "if", "are", "was"}
WRAP_UP = {  # what the interviewer says when cutting in; the reply becomes the question's follow-up
    "long": "Let me stop you there for time. In one or two sentences, what's your final answer?",
    "repeating": "I think we've covered that part. Can you sum up your approach in one sentence?",
}


def repetition(words, window=40):
    """Share of three-word phrases in the last `window` content words that already appeared earlier."""
    toks = [t for t in (_norm(w["word"]) for w in words) if t and t not in FILLERS and t not in STOPWORDS]
    if len(toks) < window + 12:
        return 0.0
    recent, earlier = toks[-window:], toks[:-window]
    seen = {tuple(earlier[i:i + 3]) for i in range(len(earlier) - 2)}
    grams = [tuple(recent[i:i + 3]) for i in range(len(recent) - 2)]
    return sum(g in seen for g in grams) / len(grams)


def ramble(words, part="main"):
    """'long', 'repeating' or None: whether the interviewer should cut in. Never about tone or emotion."""
    if not words:
        return None
    span = words[-1]["end"] - words[0]["start"]
    if span >= RAMBLE_SPEAKING_S.get(part, 120):
        return "long"
    if span >= REPEAT_MIN_S and repetition(words) >= REPEAT_RATIO:
        return "repeating"
    return None


def face_metrics(face):
    """face = {"samples": n, "face": frames with a face, "facing": frames looking at camera}."""
    samples = (face or {}).get("samples", 0)
    if not samples:
        return {"face_pct": None, "camera_pct": None}
    return {
        "face_pct": round(100 * face.get("face", 0) / samples),
        "camera_pct": round(100 * face.get("facing", 0) / samples),
    }


def delivery_metrics(words, duration_s, face=None):
    """words = [{"word", "start", "end"}] in seconds from the start of the recording."""
    out = {"duration_s": round(duration_s, 1), "word_count": len(words), **face_metrics(face)}
    if not words:
        return {**out, "wpm": None, "first_word_s": None, "pause_count": 0,
                "longest_pause_s": 0, "filler_count": 0, "fillers_per_min": None}

    span = words[-1]["end"] - words[0]["start"]
    gaps = [b["start"] - a["end"] for a, b in zip(words, words[1:])]
    pauses = [g for g in gaps if g >= PAUSE_S]
    fillers = sum(_norm(w["word"]) in FILLERS for w in words)
    measurable = span >= MIN_SPAN_S
    return {
        **out,
        "wpm": round(len(words) / span * 60) if measurable else None,
        "first_word_s": round(words[0]["start"], 1),
        "pause_count": len(pauses),
        "longest_pause_s": round(max(pauses, default=0), 1),
        "filler_count": fillers,
        "fillers_per_min": round(fillers / span * 60, 1) if measurable else None,
        "span_s": round(span, 2),
    }


def summarize(answers):
    """Session totals, weighting by speaking time and frames. Follow-up answers count as speech too."""
    done = [a for a in answers if a.get("delivery")]
    graded = [a["grade"]["final_score"] for a in answers
              if a.get("grade") and "final_score" in a["grade"]]
    takes = done + [a["follow_up"] for a in done if (a.get("follow_up") or {}).get("delivery")]
    d = [t["delivery"] for t in takes]
    span = sum(x.get("span_s", 0) for x in d)
    words = sum(x["word_count"] for x in d if x.get("span_s"))
    fillers = sum(x["filler_count"] for x in d)
    samples = sum(t.get("face", {}).get("samples", 0) for t in takes)
    facing = sum(t.get("face", {}).get("facing", 0) for t in takes)
    return {
        "answered": len(done),
        "follow_ups": len(takes) - len(done),
        "graded": len(graded),
        "content_score": round(sum(graded) / len(graded), 1) if graded else None,
        "wpm": round(words / span * 60) if span >= MIN_SPAN_S else None,
        "fillers_per_min": round(fillers / span * 60, 1) if span >= MIN_SPAN_S else None,
        "pause_count": sum(x["pause_count"] for x in d),
        "camera_pct": round(100 * facing / samples) if samples else None,
    }
