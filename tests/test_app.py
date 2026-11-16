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
    monkeypatch.setattr(answer_evaluator, "grade", lambda *a: answer_evaluator.with_final_score(json.loads(json.dumps(GRADE))))
    return app_module.app.test_client()


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
