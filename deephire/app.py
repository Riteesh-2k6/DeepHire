import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, abort, jsonify, render_template, request

import answer_evaluator
import delivery
import setup_check
import speech
from smar_selector import company_dict, difficulty_dict, domain_dict, select_questions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)
QUESTION_COUNTS = (3, 5, 10)
MODES = ("mock", "practice")  # mock: feedback at the end; practice: a quick take after each question

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024  # a 3-minute opus clip is ~1-2 MB

# ponytail: one lock for every session file; per-session locks if many people ever share a server.
# Reads take it too: on Windows, os.replace fails while another thread has the file open.
session_lock = threading.RLock()
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
    path = _session_path(session_id)
    with session_lock, open(path, encoding="utf-8") as f:
        return json.load(f)


def save_session(session):
    path = os.path.join(SESSIONS_DIR, f"{session['session_id']}.json")
    tmp = path + ".tmp"
    with session_lock:
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
    try:
        s = load_session(session_id)
        answer = s["answers"][index]
        result = answer_evaluator.grade(answer["question"], answer.get("transcript", ""), s["domain"], s["difficulty"],
                                        follow_up=answer.get("follow_up"))
    except Exception as e:  # an executor swallows errors; record it so the report can offer "Grade again"
        app.logger.exception("grading failed")
        result = {"error": f"Grading failed ({type(e).__name__})."}

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
    follow_ups = data.get("follow_ups", True)
    mode = data.get("mode", "mock")
    if company not in company_dict or domain not in domain_dict or difficulty not in difficulty_dict:
        return jsonify(error="Pick a company, a domain and a difficulty."), 400
    if count not in QUESTION_COUNTS:
        return jsonify(error=f"Number of questions must be one of {QUESTION_COUNTS}."), 400
    if not isinstance(follow_ups, bool) or mode not in MODES:
        return jsonify(error="Bad follow-up or feedback setting."), 400

    questions = select_questions(company, domain, difficulty, count)
    if not questions:
        return jsonify(error=f"There are no {domain} questions for {company} in the bank yet."), 400

    session = {
        "session_id": str(uuid.uuid4()),
        "company": company, "domain": domain, "difficulty": difficulty,
        "follow_ups": follow_ups, "mode": mode,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "answers": [{"question": q, "status": "unanswered"} for q in questions],
    }
    save_session(session)
    return jsonify(session_id=session["session_id"], redirect=f"/room?session={session['session_id']}")


@app.route("/api/answer", methods=["POST"])
def submit_answer():
    """One recorded take: the main answer (part=main) or the answer to the follow-up (part=follow_up)."""
    session_id = request.form.get("session_id")
    s = load_session(session_id)
    part = request.form.get("part", "main")
    try:
        index = int(request.form.get("index", ""))
        duration = float(request.form.get("duration", 0))
        face = json.loads(request.form.get("face") or "{}")
    except ValueError:
        return jsonify(error="Bad answer data."), 400
    if part not in ("main", "follow_up") or not 0 <= index < len(s["answers"]):
        return jsonify(error="No such question."), 400
    answer = s["answers"][index]
    if part == "follow_up" and not answer.get("follow_up"):
        return jsonify(error="No follow-up was asked for that question."), 400
    audio = request.files.get("audio")
    if not audio:
        return jsonify(error="No audio was sent."), 400

    face = {k: int(face.get(k, 0)) for k in ("samples", "face", "facing")}
    started = time.time()
    try:
        transcript, words = speech.transcribe(audio.read())  # in memory; the audio is never written to disk
    except Exception as e:  # a corrupt or empty recording shouldn't kill the interview
        app.logger.exception("transcription failed")
        return jsonify(error=f"Couldn't transcribe that recording ({type(e).__name__})."), 422
    metrics = delivery.delivery_metrics(words, duration, face)
    take = {"transcript": transcript, "words": words, "face": face, "delivery": metrics}
    app.logger.info("question %d %s: transcribed %.1f s of audio in %.1f s", index + 1, part, duration, time.time() - started)

    if part == "follow_up":
        update_session(session_id, lambda sess: sess["answers"][index]["follow_up"].update(take, status="answered"))
        queue_grading(session_id, index)
        return jsonify(transcript=transcript, delivery=metrics)

    def store(sess):
        sess["answers"][index].update(take)
        sess["answers"][index].pop("follow_up", None)  # a re-recorded answer gets a fresh follow-up
    update_session(session_id, store)

    asked = None
    if s.get("follow_ups"):
        started = time.time()
        asked = answer_evaluator.follow_up(answer["question"], transcript, s["domain"], s["difficulty"])
        app.logger.info("question %d: follow-up %s in %.1f s", index + 1, "written" if asked else "skipped", time.time() - started)
    if asked:
        def ask(sess):
            sess["answers"][index]["follow_up"] = {**asked, "status": "asked"}
            sess["answers"][index]["status"] = "awaiting_follow_up"
        update_session(session_id, ask)
    else:
        queue_grading(session_id, index)
    return jsonify(transcript=transcript, delivery=metrics, follow_up={"question": asked["question"]} if asked else None)


@app.route("/api/skip-follow-up/<session_id>/<int:index>", methods=["POST"])
def skip_follow_up(session_id, index):
    s = load_session(session_id)
    if not 0 <= index < len(s["answers"]) or s["answers"][index].get("status") != "awaiting_follow_up":
        return jsonify(error="That question isn't waiting on a follow-up."), 400
    update_session(session_id, lambda sess: sess["answers"][index]["follow_up"].update(status="skipped"))
    queue_grading(session_id, index)
    return jsonify(ok=True)


@app.route("/api/finish/<session_id>", methods=["POST"])
def finish_interview(session_id):
    """Ending mid-exchange: grade what was said, as if the open follow-up were skipped."""
    s = load_session(session_id)
    pending = [i for i, a in enumerate(s["answers"]) if a.get("status") == "awaiting_follow_up"]
    for i in pending:
        update_session(session_id, lambda sess, i=i: sess["answers"][i]["follow_up"].update(status="skipped"))
        queue_grading(session_id, i)
    return jsonify(queued=len(pending))


def _warm_up_models():
    speech.load()                 # Whisper: a few seconds from the local cache
    answer_evaluator.warm_up()    # llama-swap loads gpt-oss-20b on its first request: ~20 s warm, ~2 min cold


@app.route("/api/warmup", methods=["POST"])
def warmup():
    # The room calls this as it opens, so both models are ready by the first answer.
    threading.Thread(target=_warm_up_models, daemon=True).start()
    return jsonify(ok=True)


@app.route("/api/camera-check", methods=["POST"])
def camera_check():
    frame = request.files.get("frame")
    data = frame.read() if frame else b""
    if not data or len(data) > 3 * 1024 * 1024:
        return jsonify(error="Send one JPEG frame under 3 MB."), 400
    result = setup_check.check_frame(data)  # the frame is only held in memory for this call
    return jsonify(result), (502 if "error" in result else 200)


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
        session={k: s.get(k) for k in ("session_id", "company", "domain", "difficulty", "created_at", "follow_ups", "mode")},
        answers=s["answers"],
        summary=delivery.summarize(s["answers"]),
        ranges=delivery.RANGES,
        pause_s=delivery.PAUSE_S,
        grading=sum(a.get("status") == "grading" for a in s["answers"]),
    )


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    # threaded so the report can poll while an answer is being transcribed
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", threaded=True)
