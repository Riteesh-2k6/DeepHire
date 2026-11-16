from delivery import delivery_metrics, face_metrics, summarize


def w(word, start, end):
    return {"word": word, "start": start, "end": end}


# 12 words over 6.0 s, one 2.5 s pause, two fillers ("Um," and "uh")
WORDS = [w("Um,", 1.0, 1.3), w("I", 1.4, 1.5), w("would", 1.5, 1.8), w("use", 1.8, 2.0),
         w("a", 2.0, 2.1), w("hash", 2.1, 2.4), w("map.", 2.4, 2.8),
         w("uh", 5.3, 5.5), w("then", 5.6, 5.9), w("sort", 5.9, 6.2), w("the", 6.2, 6.4), w("counts.", 6.4, 7.0)]


def test_pace_pauses_fillers():
    m = delivery_metrics(WORDS, duration_s=8.0, face={"samples": 40, "face": 36, "facing": 30})
    assert m["word_count"] == 12
    assert m["wpm"] == 120                      # 12 words / 6.0 s
    assert m["first_word_s"] == 1.0
    assert m["pause_count"] == 1 and m["longest_pause_s"] == 2.5
    assert m["filler_count"] == 2
    assert m["fillers_per_min"] == 20.0         # 2 fillers / 6.0 s
    assert (m["face_pct"], m["camera_pct"]) == (90, 75)


def test_short_or_silent_answers_have_no_pace():
    short = delivery_metrics(WORDS[:3], duration_s=2.0)
    assert short["wpm"] is None and short["fillers_per_min"] is None
    silent = delivery_metrics([], duration_s=10.0)
    assert silent["word_count"] == 0 and silent["wpm"] is None and silent["pause_count"] == 0


def test_no_camera_means_no_face_numbers():
    assert face_metrics(None) == {"face_pct": None, "camera_pct": None}
    assert face_metrics({"samples": 0}) == {"face_pct": None, "camera_pct": None}


def test_summary_weights_by_speaking_time_and_frames():
    a = {"delivery": delivery_metrics(WORDS, 8.0), "face": {"samples": 10, "facing": 10},
         "grade": {"final_score": 8.0}}
    b = {"delivery": delivery_metrics(WORDS, 8.0), "face": {"samples": 30, "facing": 0},
         "grade": {"error": "model down"}}
    skipped = {"question": "q", "status": "unanswered"}
    s = summarize([a, b, skipped])
    assert s["answered"] == 2 and s["graded"] == 1
    assert s["content_score"] == 8.0            # the failed grade is left out, not counted as 0
    assert s["wpm"] == 120 and s["pause_count"] == 2
    assert s["camera_pct"] == 25                # 10 of 40 frames, not the mean of 100% and 0%
