import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, abort, jsonify, render_template, request

import answer_evaluator
import delivery
import speech
from smar_selector import company_dict, difficulty_dict, domain_dict, select_questions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)
QUESTION_COUNTS = (3, 5, 10)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024  # a 3-minute opus clip is ~1-2 MB

# ponytail: one lock for every session file; per-session locks if many people ever share a server.
session_lock = threading.Lock()
# One grading call at a time: they all share one local GPU.
grader = ThreadPoolExecutor(max_workers=1)


# ---------- session files ----------

def _session_path(session_id):
    try:
        uuid.UUID(str(session_id))  # ids are uuid4s we issue; this also blocks path tricks
    except ValueError:
        abort(404)
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        abort(404)
    return path


def load_session(session_id):
    with open(_session_path(session_id), encoding="utf-8") as f:
        return json.load(f)


def save_session(session):
    path = os.path.join(SESSIONS_DIR, f"{session['session_id']}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)
    os.replace(tmp, path)  # never leave a half-written file


def update_session(session_id, change):
    with session_lock:
        session = load_session(session_id)
        change(session)
        save_session(session)
        return session


# ---------- grading ----------

def grade_answer(session_id, index):
    s = load_session(session_id)
    answer = s["answers"][index]
    result = answer_evaluator.grade(answer["question"], answer.get("transcript", ""), s["domain"], s["difficulty"])

    def store(session):
        session["answers"][index]["grade"] = result
        session["answers"][index]["status"] = "error" if "error" in result else "graded"
    update_session(session_id, store)


def queue_grading(session_id, index):
    def mark(session):
        session["answers"][index]["status"] = "grading"
        session["answers"][index]["grade"] = None
    update_session(session_id, mark)
    grader.submit(grade_answer, session_id, index)


# ---------- pages ----------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/blog")
def blog():
    return render_template("blog.html")


def _blog_page(n):
    return lambda: render_template(f"blogs/blog{n}.html")


for _n in range(1, 10):
    app.add_url_rule(f"/blog{_n}", f"blog{_n}", _blog_page(_n))


@app.route("/interview")
def interview():
    companies = [c for c in company_dict if c != "Netflix"]  # Netflix has no questions in the bank yet
    return render_template("interview.html", companies=companies, domains=list(domain_dict),
                           difficulties=list(difficulty_dict), counts=QUESTION_COUNTS)


@app.route("/room")
def room():
    return render_template("room.html", session=load_session(request.args.get("session")))


@app.route("/report")
def report():
    return render_template("report.html", session=load_session(request.args.get("session")))


# ---------- API ----------

@app.route("/submit-interview-preferences", methods=["POST"])
def submit_interview_preferences():
    data = request.get_json(silent=True) or {}
    company, domain, difficulty = data.get("company"), data.get("domain"), data.get("difficulty")
    count = data.get("count", 5)
    if company not in company_dict or domain not in domain_dict or difficulty not in difficulty_dict:
        return jsonify(error="Pick a company, a domain and a difficulty."), 400
    if count not in QUESTION_COUNTS:
        return jsonify(error=f"Number of questions must be one of {QUESTION_COUNTS}."), 400

    questions = select_questions(company, domain, difficulty, count)
    if not questions:
        return jsonify(error=f"There are no {domain} questions for {company} in the bank yet."), 400

    session = {
        "session_id": str(uuid.uuid4()),
        "company": company, "domain": domain, "difficulty": difficulty,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "answers": [{"question": q, "status": "unanswered"} for q in questions],
    }
    save_session(session)
    return jsonify(session_id=session["session_id"], redirect=f"/room?session={session['session_id']}")


@app.route("/api/answer", methods=["POST"])
def submit_answer():
    session_id = request.form.get("session_id")
    s = load_session(session_id)
    try:
        index = int(request.form.get("index", ""))
        duration = float(request.form.get("duration", 0))
        face = json.loads(request.form.get("face") or "{}")
    except ValueError:
        return jsonify(error="Bad answer data."), 400
    if not 0 <= index < len(s["answers"]):
        return jsonify(error="No such question."), 400
    audio = request.files.get("audio")
    if not audio:
        return jsonify(error="No audio was sent."), 400

    face = {k: int(face.get(k, 0)) for k in ("samples", "face", "facing")}
    try:
        transcript, words = speech.transcribe(audio.read())  # in memory; the audio is never written to disk
    except Exception as e:  # a corrupt or empty recording shouldn't kill the interview
        app.logger.exception("transcription failed")
        return jsonify(error=f"Couldn't transcribe that recording ({type(e).__name__})."), 422

    metrics = delivery.delivery_metrics(words, duration, face)

    def store(session):
        session["answers"][index].update(transcript=transcript, words=words, face=face, delivery=metrics)
    update_session(session_id, store)
    queue_grading(session_id, index)
    return jsonify(transcript=transcript, delivery=metrics)


@app.route("/api/regrade/<session_id>/<int:index>", methods=["POST"])
def regrade(session_id, index):
    s = load_session(session_id)
    if not 0 <= index < len(s["answers"]) or "transcript" not in s["answers"][index]:
        return jsonify(error="Nothing to grade for that question."), 400
    queue_grading(session_id, index)
    return jsonify(ok=True)


@app.route("/api/report/<session_id>")
def report_data(session_id):
    s = load_session(session_id)
    return jsonify(
        session={k: s[k] for k in ("session_id", "company", "domain", "difficulty", "created_at")},
        answers=s["answers"],
        summary=delivery.summarize(s["answers"]),
        ranges=delivery.RANGES,
        pause_s=delivery.PAUSE_S,
        grading=sum(a.get("status") == "grading" for a in s["answers"]),
    )


if __name__ == "__main__":
    # threaded so the report can poll while an answer is being transcribed
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", threaded=True)
