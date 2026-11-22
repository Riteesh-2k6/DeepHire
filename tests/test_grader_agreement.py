import importlib.util
import pathlib

import answer_evaluator

spec = importlib.util.spec_from_file_location("grader_agreement", pathlib.Path(__file__).parent.parent / "scripts" / "grader_agreement.py")
ga = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ga)

CASES = [{"id": "c01", "kind": "good", "source": "synthetic", "domain": "Python", "difficulty": "Easy", "question": "Q1?", "transcript": "good"},
         {"id": "c02", "kind": "off_topic", "source": "saved", "domain": "Python", "difficulty": "Easy", "question": "Q2?", "transcript": "other"},
         {"id": "c03", "kind": "weak", "source": "synthetic", "domain": "Python", "difficulty": "Easy", "question": "Q3?", "transcript": "meh"}]
SCORES = {"good": 8.5, "other": 9.0, "meh": 4.4}


def test_model_run_resumes_and_report_counts_agreement(tmp_path, monkeypatch):
    for name, value in {"CASES": CASES, "HUMAN": tmp_path / "h.csv", "MODEL": tmp_path / "m.json", "RESULTS": tmp_path / "r.md"}.items():
        monkeypatch.setattr(ga, name, value)
    calls = []
    monkeypatch.setattr(answer_evaluator, "grade", lambda q, t, *a: calls.append(t) or {"final_score": SCORES[t], "on_topic": True})

    version = ga.grade_with_model()
    assert ga.grade_with_model() == version and len(calls) == 3  # second run: everything cached

    assert ga.human_scores() == {}  # the blank sheet was written
    ga.report(version, {})
    assert "Waiting for human grades" in ga.RESULTS.read_text(encoding="utf-8")

    rows = ga.read_sheet()
    for r, s in zip(rows, ["9", "1", "2"]):
        r["score"] = s
    ga.write_sheet(rows)
    ga.report(version, ga.human_scores())
    text = ga.RESULTS.read_text(encoding="utf-8")
    assert "**c02** (off_topic, 9.0" in text  # off-topic scored high is listed
    assert "Exact: 1/3" in text and "Within ±1: 1/3" in text  # 8.5 rounds up to 9; 4.4 vs 2 and 9 vs 1 miss
    assert "c02 (off_topic): model 9.0, human 1" in text
    assert ga.rounded(6.5) == 7 and ga.band(6.5) == 3
