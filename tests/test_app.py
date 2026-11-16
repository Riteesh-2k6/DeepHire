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


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "SESSIONS_DIR", str(tmp_path))
    words = [{"word": "Um,", "start": 0.5, "end": 0.8}, {"word": "use", "start": 1.0, "end": 1.2},
             {"word": "a", "start": 1.2, "end": 1.3}, {"word": "heap.", "start": 6.0, "end": 6.5}]
    monkeypatch.setattr(speech, "transcribe", lambda audio: ("Um, use a heap.", words))
    graded_with = []

    def fake_grade(*a, follow_up=None):
        graded_with.append(follow_up)
        return answer_evaluator.with_final_score(json.loads(json.dumps(GRADE)))
    monkeypatch.setattr(answer_evaluator, "grade", fake_grade)
    monkeypatch.setattr(answer_evaluator, "follow_up", lambda *a: None)  # tests that want one override this
    c = app_module.app.test_client()
    c.graded_with = graded_with
    return c


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


def test_follow_up_is_asked_then_the_exchange_is_graded(client, monkeypatch):
    monkeypatch.setattr(answer_evaluator, "follow_up", lambda *a: {"question": "Why a heap?", "probes": "trade-off"})
    sid = start(client, mode="practice").get_json()["session_id"]

    r = post_take(client, sid, 0)
    assert r.get_json()["follow_up"] == {"question": "Why a heap?"}
    drain()
    data = client.get(f"/api/report/{sid}").get_json()
    assert data["answers"][0]["status"] == "awaiting_follow_up"          # not graded until the follow-up
    assert data["session"]["mode"] == "practice"

    assert post_take(client, sid, 0, part="follow_up").status_code == 200
    drain()
    data = client.get(f"/api/report/{sid}").get_json()
    assert data["answers"][0]["status"] == "graded"
    assert client.graded_with[-1]["question"] == "Why a heap?"           # graded as one exchange
    assert client.graded_with[-1]["transcript"] == "Um, use a heap."
    assert data["summary"]["follow_ups"] == 1


def test_skipping_or_ending_grades_what_was_said(client, monkeypatch):
    monkeypatch.setattr(answer_evaluator, "follow_up", lambda *a: {"question": "Why?", "probes": ""})
    sid = start(client).get_json()["session_id"]
    post_take(client, sid, 0)
    post_take(client, sid, 1)
    assert client.post(f"/api/skip-follow-up/{sid}/0").status_code == 200
    assert client.post(f"/api/skip-follow-up/{sid}/2").status_code == 400  # nothing asked there
    assert client.post(f"/api/finish/{sid}").get_json() == {"queued": 1}  # question 2 was mid-exchange
    drain()
    answers = client.get(f"/api/report/{sid}").get_json()["answers"]
    assert [a["status"] for a in answers] == ["graded", "graded", "unanswered"]
    assert answers[0]["follow_up"]["status"] == "skipped"


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
