import io
import json

import pytest

import answer_evaluator
import app as app_module
import speech

GRADE = {"model_answer": "Use a heap.", "feedback": "Mention edge cases.",
         "technical_accuracy": {"score": 8, "justification": "ok"},
         "problem_solving": {"score": 6, "justification": "ok"},
         "completeness": {"score": "5", "justification": "ok"},
         "optimization": {"score": 14, "justification": "clamped"},
         "clarity": {"score": 7, "justification": "ok"}}


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


def test_weighted_score_is_computed_not_trusted():
    g = answer_evaluator.with_final_score(json.loads(json.dumps(GRADE)))
    assert g["optimization"]["score"] == 10      # clamped from 14
    assert g["final_score"] == 7.0               # .4*8 + .3*6 + .2*5 + .1*10


def test_off_topic_answers_are_capped():
    g = answer_evaluator.with_final_score({**json.loads(json.dumps(GRADE)), "on_topic": False})
    assert max(g[k]["score"] for k in answer_evaluator.CRITERIA) == 2.0
    assert g["final_score"] == 2.0


def test_grade_handles_bad_json_and_empty_transcripts():
    bad = answer_evaluator.grade("q", "some answer", post=lambda *a, **k: FakeResponse("not json"))
    assert "error" in bad
    assert "error" in answer_evaluator.grade("q", "   ")


def test_a_grade_with_scores_missing_is_retried_and_never_reads_as_zero():
    partial = json.dumps({"candidate_summary": "You said you'd use Redis.", "feedback": "..."})
    replies = iter([partial, json.dumps(GRADE)])
    assert answer_evaluator.grade("q", "some answer", post=lambda *a, **k: FakeResponse(next(replies)))["final_score"] == 7.0
    assert "error" in answer_evaluator.grade("q", "some answer", post=lambda *a, **k: FakeResponse(partial))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "SESSIONS_DIR", str(tmp_path))
    words = [{"word": "Um,", "start": 0.5, "end": 0.8}, {"word": "use", "start": 1.0, "end": 1.2},
             {"word": "a", "start": 1.2, "end": 1.3}, {"word": "heap.", "start": 6.0, "end": 6.5}]
    monkeypatch.setattr(speech, "transcribe", lambda audio: ("Um, use a heap.", words))
    graded_follow_ups = []

    def fake_follow_up_grade(question, transcript, follow_q, follow_transcript, domain=""):
        graded_follow_ups.append((follow_q, follow_transcript))
        return {"score": 6.0, "justification": "You named the trade-off."}
    monkeypatch.setattr(answer_evaluator, "grade", lambda *a: answer_evaluator.with_final_score(json.loads(json.dumps(GRADE))))
    monkeypatch.setattr(answer_evaluator, "grade_follow_up", fake_follow_up_grade)
    monkeypatch.setattr(answer_evaluator, "follow_up", lambda *a: None)  # tests that want one override this
    monkeypatch.setattr(app_module, "tts_prefetch", lambda text, lane="now": None)  # no voice model in tests
    c = app_module.app.test_client()
    c.graded_follow_ups = graded_follow_ups
    yield c
    drain()  # no grading job may outlive its test's stubs


def start(client, **overrides):
    body = {"company": "Google", "domain": "Python", "difficulty": "Medium", "count": 3, **overrides}
    return client.post("/submit-interview-preferences", json=body)


def test_interview_flow(client):
    r = start(client)
    assert r.status_code == 200
    sid = r.get_json()["session_id"]
    assert client.get(f"/room?session={sid}").status_code == 200

    r = client.post("/api/answer", data={
        "session_id": sid, "index": "1", "duration": "7.5",
        "face": json.dumps({"samples": 20, "face": 20, "facing": 15}),
        "audio": (io.BytesIO(b"fake webm"), "answer.webm")})
    assert r.status_code == 200
    assert r.get_json()["delivery"]["pause_count"] == 1      # the 4.7 s gap

    app_module.grader.submit(lambda: None).result()          # single worker: earlier jobs are done
    data = client.get(f"/api/report/{sid}").get_json()
    assert len(data["answers"]) == 3 and data["grading"] == 0
    assert data["answers"][1]["status"] == "graded"
    assert data["answers"][0]["status"] == "unanswered"
    assert data["summary"]["content_score"] == 7.0
    assert data["summary"]["camera_pct"] == 75
    assert client.get(f"/report?session={sid}").status_code == 200


def test_bad_requests(client):
    assert start(client, count=7).status_code == 400
    assert start(client, company="Nokia").status_code == 400
    assert start(client, company="Netflix").status_code == 400            # no questions in the bank
    sid = start(client).get_json()["session_id"]
    bad_index = client.post("/api/answer", data={"session_id": sid, "index": "9",
                                                 "audio": (io.BytesIO(b"x"), "a.webm")})
    assert bad_index.status_code == 400
    assert client.get("/api/report/not-a-uuid").status_code == 404
    assert client.get("/room?session=../../etc/passwd").status_code == 404


# ---------- M2: follow-ups, modes, camera check ----------

def post_take(client, sid, index, part="main"):
    return client.post("/api/answer", data={"session_id": sid, "index": str(index), "part": part, "duration": "7",
                                            "face": "{}", "audio": (io.BytesIO(b"fake webm"), "a.webm")})


def drain():
    app_module.grader.submit(lambda: None).result()


def test_main_answer_is_graded_at_once_and_the_follow_up_separately(client, monkeypatch):
    monkeypatch.setattr(answer_evaluator, "follow_up", lambda *a: {"question": "Why a heap?", "probes": "trade-off"})
    sid = start(client, mode="practice").get_json()["session_id"]

    r = post_take(client, sid, 0)
    assert r.get_json()["follow_up"] == {"question": "Why a heap?"}
    drain()
    data = client.get(f"/api/report/{sid}").get_json()
    assert data["answers"][0]["status"] == "graded"                       # no waiting for the follow-up
    assert data["answers"][0]["follow_up"]["status"] == "asked"
    assert data["session"]["mode"] == "practice"

    assert post_take(client, sid, 0, part="follow_up").status_code == 200
    drain()
    data = client.get(f"/api/report/{sid}").get_json()
    f = data["answers"][0]["follow_up"]
    assert f["status"] == "graded" and f["grade"]["score"] == 6.0
    assert client.graded_follow_ups == [("Why a heap?", "Um, use a heap.")]
    assert data["summary"]["follow_ups"] == 1 and data["summary"]["content_score"] == 7.0  # main rubric only


def test_skipping_or_ending_grades_what_was_said(client, monkeypatch):
    monkeypatch.setattr(answer_evaluator, "follow_up", lambda *a: {"question": "Why?", "probes": ""})
    sid = start(client).get_json()["session_id"]
    post_take(client, sid, 0)
    post_take(client, sid, 1)
    assert client.post(f"/api/skip-follow-up/{sid}/0").status_code == 200
    assert client.post(f"/api/skip-follow-up/{sid}/2").status_code == 400  # nothing asked there
    assert client.post(f"/api/finish/{sid}").get_json() == {"closed": 1}  # question 2 was mid-exchange
    drain()
    answers = client.get(f"/api/report/{sid}").get_json()["answers"]
    assert [a["status"] for a in answers] == ["graded", "graded", "unanswered"]
    assert [a.get("follow_up", {}).get("status") for a in answers] == ["skipped", "skipped", None]


def test_follow_ups_off_and_bad_settings(client, monkeypatch):
    monkeypatch.setattr(answer_evaluator, "follow_up", lambda *a: pytest.fail("follow-ups are off"))
    sid = start(client, follow_ups=False).get_json()["session_id"]
    assert post_take(client, sid, 0).get_json()["follow_up"] is None
    assert post_take(client, sid, 0, part="follow_up").status_code == 400  # none was asked
    assert start(client, mode="exam").status_code == 400
    assert start(client, follow_ups="yes").status_code == 400


def test_follow_up_text_is_cleaned():
    clean = answer_evaluator.clean_follow_up
    assert clean("  Why a heap?  And what about memory?", "q") == "Why a heap?"
    assert clean("What is the worst case", "q") == "What is the worst case?"
    assert clean("Implement a trie?", "Implement a trie.") is None             # an echo of the question
    assert clean("ok", "q") is None and clean(None, "q") is None
    fake = lambda *a, **k: FakeResponse(json.dumps({"follow_up": "How would you handle deletes", "probes": "edge case"}))
    assert answer_evaluator.follow_up("Implement a trie.", "I would use a dict per node", post=fake) == \
        {"question": "How would you handle deletes?", "probes": "edge case"}
    assert answer_evaluator.follow_up("Implement a trie.", "um", post=fake) is None  # nothing said


def test_camera_tips_never_describe_the_person():
    import setup_check
    tips = setup_check.keep_setup_tips([
        "The window behind you backlights the frame; face the light instead.",
        "You look nervous; try to relax.",
        "Raise the camera to eye level.",
        "Your hair is covering your eyes.",
        "Raise the camera to eye level.",
        42])
    assert tips == ["The window behind you backlights the frame; face the light instead.", "Raise the camera to eye level."]  # 42 is too short to be a tip
    fake = lambda *a, **k: FakeResponse(json.dumps({"tips": ["You seem confident!", "Move back a little so your shoulders show."]}))
    assert setup_check.check_frame(b"jpeg", post=fake) == {"tips": ["Move back a little so your shoulders show."]}


def test_follow_up_has_a_hard_deadline():
    import time as _time

    def trickling_server(*a, **k):          # never times out at the socket level, just takes too long
        _time.sleep(1.0)
        return FakeResponse(json.dumps({"follow_up": "Too late?"}))
    t = _time.time()
    assert answer_evaluator.follow_up("q", "a real answer here", post=trickling_server, timeout=0.2) is None
    assert _time.time() - t < 0.8


# ---------- live transcription, interruptions, the voice ----------

def test_cuts_land_in_pauses_after_speech():
    import numpy as np
    import stream
    loud, quiet = 0.2, 0.001
    rms = np.array([quiet] * 10 + [loud] * 40 + [quiet] * 20 + [loud] * 30)   # thinking, speech, 0.6 s pause, speech
    assert stream.find_cut(rms, 0.01, pause_frames=16, max_frames=400) == 60    # middle of the pause
    assert stream.find_cut(rms[:55], 0.01, 16, 400) is None                     # pause not long enough yet
    assert stream.find_cut(np.array([loud] * 450), 0.01, 16, 400) is not None   # no pause at all: forced cut


def test_live_stream_feeds_the_final_transcript(client, monkeypatch):
    import numpy as np
    import stream
    calls = []

    def fake_segment(audio, offset_s=0.0, context=""):
        calls.append(round(offset_s, 2))
        return [{"word": "segment", "start": round(offset_s + 0.1, 2), "end": round(offset_s + 0.4, 2)}]
    monkeypatch.setattr(stream.speech, "transcribe_array", fake_segment)
    monkeypatch.setattr(speech, "transcribe", lambda audio: pytest.fail("the full pass must not run"))
    sid = start(client).get_json()["session_id"]
    tone = (np.sin(np.arange(16000) / 3) * 8000).astype("<i2").tobytes()       # 1 s of "speech"
    hush = np.zeros(16000, "<i2").tobytes()                                     # 1 s of silence
    for seq, chunk in enumerate([tone, hush, tone]):
        r = client.post(f"/api/stream/{sid}/0/main?seq={seq}", data=chunk)
        assert r.status_code == 200 and "text" in r.get_json()
    r = client.post("/api/answer", data={"session_id": sid, "index": "0", "duration": "3", "streamed": "1", "face": "{}"})
    assert r.status_code == 200
    assert r.get_json()["transcript"] == "segment segment"                      # two stretches of speech
    assert calls[0] == 0.0 and calls[1] > 1.0                                    # the second carries its offset


def test_a_lost_chunk_falls_back_to_the_full_recording(client, monkeypatch):
    import numpy as np
    import stream
    monkeypatch.setattr(stream.speech, "transcribe_array", lambda *a, **k: [])
    sid = start(client).get_json()["session_id"]
    chunk = np.zeros(1600, "<i2").tobytes()
    client.post(f"/api/stream/{sid}/0/main?seq=0", data=chunk)
    client.post(f"/api/stream/{sid}/0/main?seq=2", data=chunk)                  # seq 1 never arrived
    r = client.post("/api/answer", data={"session_id": sid, "index": "0", "duration": "7", "streamed": "1",
                                         "face": "{}", "audio": (io.BytesIO(b"webm"), "a.webm")})
    assert r.get_json()["transcript"] == "Um, use a heap."                      # from the full pass


def test_rambling_is_measured_not_judged():
    import delivery

    def say(text, every=0.5, start=0.0):
        return [{"word": w, "start": start + i * every, "end": start + i * every + 0.3} for i, w in enumerate(text.split())]
    word = lambda i: "".join(chr(97 + (i // 26 ** k) % 26) for k in range(3))   # aaa, baa, caa... all distinct
    varied = " ".join(word(i) for i in range(260))                              # 260 words, 0.5 s apart: 130 s
    assert delivery.ramble(say(varied), "main") == "long"
    assert delivery.ramble(say(varied)[:150], "main") is None                   # 75 s of varied speech is fine
    assert delivery.ramble(say("short answer about heaps"), "main") is None
    loop = "we use a hash map to count words and sort the counts " * 12
    assert delivery.repetition(say(loop)) > delivery.REPEAT_RATIO
    assert delivery.ramble(say(loop, every=0.45), "main") == "repeating"
    assert delivery.repetition(say(varied)) == 0.0


def test_an_interruption_becomes_the_follow_up(client, monkeypatch):
    import delivery
    monkeypatch.setattr(answer_evaluator, "follow_up", lambda *a: pytest.fail("no model call when interrupting"))
    sid = start(client).get_json()["session_id"]
    r = client.post("/api/answer", data={"session_id": sid, "index": "0", "duration": "130", "face": "{}",
                                         "interrupted": "long", "audio": (io.BytesIO(b"webm"), "a.webm")})
    assert r.get_json()["follow_up"]["question"] == delivery.WRAP_UP["long"]
    drain()
    a = client.get(f"/api/report/{sid}").get_json()["answers"][0]
    assert a["interrupted"] == "long" and a["follow_up"]["kind"] == "wrap_up" and a["status"] == "graded"
    bad = client.post("/api/answer", data={"session_id": sid, "index": "1", "duration": "5", "face": "{}",
                                           "interrupted": "boring", "audio": (io.BytesIO(b"webm"), "a.webm")})
    assert bad.status_code == 400


def test_speech_endpoint(client, monkeypatch):
    import tts
    monkeypatch.setattr(tts, "available", lambda: False)
    assert client.post("/api/speech", json={"text": "Hello there."}).status_code == 503   # room falls back
    monkeypatch.setattr(tts, "available", lambda: True)
    monkeypatch.setattr(tts, "speak", lambda text, *a: b"RIFF....WAVE")
    r = client.post("/api/speech", json={"text": "Hello there."})
    assert r.status_code == 200 and r.mimetype == "audio/wav"
    assert client.post("/api/speech", json={"text": ""}).status_code == 400
    assert tts.sentences("First one. Second one? Third!") == ["First one.", "Second one?", "Third!"]


# ---------- desktop app: settings, history, pages ----------

@pytest.fixture
def fresh_settings(tmp_path, monkeypatch):
    import settings
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(settings, "_cache", None)
    return settings


def test_settings_validate_and_persist(fresh_settings, client):
    s = fresh_settings
    with pytest.raises(ValueError):
        s.update({"tts_voice": "robot"})
    with pytest.raises(ValueError):
        s.update({"llm_base_url": "ftp://nope"})
    with pytest.raises(ValueError):
        s.update({"no_such_setting": 1})
    s.update({"tts_speed": 1.1, "count": 3, "llm_base_url": "http://127.0.0.1:9000/v1/"})
    assert json.load(open(s.PATH))["llm_base_url"] == "http://127.0.0.1:9000/v1"   # saved, trailing slash gone
    s._cache = None
    assert s.get("count") == 3 and s.get("tts_speed") == 1.1                      # reloaded from disk
    assert client.post("/api/settings", json={"mode": "exam"}).status_code == 400
    assert client.post("/api/settings", json={"mode": "practice"}).get_json()["mode"] == "practice"
    sid = start(client, mode=None).get_json()                                     # a bad explicit value is refused
    assert "error" in sid


def test_new_sessions_start_from_saved_defaults(fresh_settings, client):
    fresh_settings.update({"count": 10, "follow_ups": False, "mode": "practice"})
    r = client.post("/submit-interview-preferences", json={"company": "Google", "domain": "Python", "difficulty": "Easy"})
    data = client.get(f"/api/report/{r.get_json()['session_id']}").get_json()
    assert len(data["answers"]) == 10
    assert data["session"]["follow_ups"] is False and data["session"]["mode"] == "practice"


def test_history_lists_and_deletes(client):
    first = start(client).get_json()["session_id"]
    second = start(client, company="Amazon").get_json()["session_id"]
    post_take(client, second, 0)
    drain()
    listed = client.get("/api/sessions").get_json()["sessions"]
    assert {s["session_id"] for s in listed} == {first, second}
    amazon = next(s for s in listed if s["session_id"] == second)
    assert amazon["summary"]["answered"] == 1 and amazon["questions"] == 3
    assert client.delete(f"/api/sessions/{first}").status_code == 200
    assert [s["session_id"] for s in client.get("/api/sessions").get_json()["sessions"]] == [second]
    assert client.delete(f"/api/sessions/{first}").status_code == 404


def test_app_pages(client):
    assert client.get("/").headers["Location"].endswith("/practice")
    for page in ("/practice", "/history", "/settings"):
        r = client.get(page)
        assert r.status_code == 200 and b'class="rail"' in r.data
    sid = start(client).get_json()["session_id"]
    assert b'class="rail"' not in client.get(f"/room?session={sid}").data   # the room takes the whole window
