import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import Flask, abort, jsonify, redirect, render_template, request

import answer_evaluator
import delivery
import settings
import setup_check
import speech
import stream
import tts
from smar_selector import company_dict, difficulty_dict, domain_dict, select_questions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# The desktop app keeps sessions in %LOCALAPPDATA%\DeepHire (settings.DATA_DIR); a dev run keeps them here.
SESSIONS_DIR = os.path.join(settings.DATA_DIR, "sessions")
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
        result = answer_evaluator.grade(answer["question"], answer.get("transcript", ""), s["domain"], s["difficulty"])
    except Exception as e:  # an executor swallows errors; record it so the report can offer "Grade again"
        app.logger.exception("grading failed")
        result = {"error": f"Grading failed ({type(e).__name__})."}

    def store(session):
        session["answers"][index]["grade"] = result
        session["answers"][index]["status"] = "error" if "error" in result else "graded"
    update_session(session_id, store)


def grade_follow_up(session_id, index):
    try:
        s = load_session(session_id)
        a = s["answers"][index]
        f = a["follow_up"]
        result = answer_evaluator.grade_follow_up(a["question"], a.get("transcript", ""), f["question"],
                                                  f.get("transcript", ""), s["domain"])
    except Exception as e:
        app.logger.exception("follow-up grading failed")
        result = {"error": f"Grading failed ({type(e).__name__})."}

    def store(session):
        session["answers"][index]["follow_up"].update(grade=result, status="error" if "error" in result else "graded")
    update_session(session_id, store)


def queue_grading(session_id, index, part="main"):
    def mark(session):
        target = session["answers"][index] if part == "main" else session["answers"][index]["follow_up"]
        target["status"] = "grading"
        target["grade"] = None
    update_session(session_id, mark)
    grader.submit(grade_answer if part == "main" else grade_follow_up, session_id, index)


# ---------- pages ----------

@app.route("/")
def index():
    return redirect("/practice")


@app.route("/about")
def about():
    return render_template("index.html")   # the 2025 landing page, not linked from the app


@app.route("/blog")
def blog():
    return render_template("blog.html")


def _blog_page(n):
    return lambda: render_template(f"blogs/blog{n}.html")


for _n in range(1, 10):
    app.add_url_rule(f"/blog{_n}", f"blog{_n}", _blog_page(_n))


@app.route("/practice")
@app.route("/interview")
def interview():
    companies = [c for c in company_dict if c != "Netflix"]  # Netflix has no questions in the bank yet
    return render_template("interview.html", companies=companies, domains=list(domain_dict),
                           difficulties=list(difficulty_dict), counts=QUESTION_COUNTS,
                           defaults=settings.all_settings(), page="practice")


@app.route("/history")
def history():
    return render_template("history.html", page="history")


@app.route("/settings")
def settings_page():
    return render_template("settings.html", page="settings", voices=settings.VOICES,
                           whisper_models=settings.WHISPER_MODELS, data_dir=settings.DATA_DIR,
                           voice_ready=tts.available())


@app.route("/room")
def room():
    return render_template("room.html", session=load_session(request.args.get("session")), wrap_up=delivery.WRAP_UP)


@app.route("/report")
def report():
    return render_template("report.html", session=load_session(request.args.get("session")), page="history")


# ---------- API ----------

@app.route("/submit-interview-preferences", methods=["POST"])
def submit_interview_preferences():
    data = request.get_json(silent=True) or {}
    company, domain, difficulty = data.get("company"), data.get("domain"), data.get("difficulty")
    defaults = settings.all_settings()
    count = data.get("count", defaults["count"])
    follow_ups = data.get("follow_ups", defaults["follow_ups"])
    interruptions = data.get("interruptions", defaults["interruptions"])
    mode = data.get("mode", defaults["mode"])
    if company not in company_dict or domain not in domain_dict or difficulty not in difficulty_dict:
        return jsonify(error="Pick a company, a domain and a difficulty."), 400
    if count not in QUESTION_COUNTS:
        return jsonify(error=f"Number of questions must be one of {QUESTION_COUNTS}."), 400
    if not isinstance(follow_ups, bool) or not isinstance(interruptions, bool) or mode not in MODES:
        return jsonify(error="Bad follow-up or feedback setting."), 400

    questions = select_questions(company, domain, difficulty, count)
    if not questions:
        return jsonify(error=f"There are no {domain} questions for {company} in the bank yet."), 400

    session = {
        "session_id": str(uuid.uuid4()),
        "company": company, "domain": domain, "difficulty": difficulty,
        "follow_ups": follow_ups, "mode": mode, "interruptions": interruptions,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "answers": [{"question": q, "status": "unanswered"} for q in questions],
    }
    save_session(session)
    tts_prefetch(questions[0], lane="ahead")   # voiced during the sound check
    return jsonify(session_id=session["session_id"], redirect=f"/room?session={session['session_id']}")


@app.route("/api/stream/<session_id>/<int:index>/<part>", methods=["POST"])
def stream_chunk(session_id, index, part):
    """A 16 kHz PCM chunk of the answer in progress. Returns the live caption and whether to cut in."""
    _session_path(session_id)  # validates the id
    if part not in ("main", "follow_up"):
        return jsonify(error="Bad part."), 400
    try:
        seq = int(request.args.get("seq", ""))
    except ValueError:
        return jsonify(error="Bad sequence number."), 400
    data = request.get_data()
    if len(data) > stream.RATE * 2 * 10:   # more than 10 s in one chunk isn't a live stream
        return jsonify(error="Chunk too large."), 413
    live = stream.add_chunk(stream.key(session_id, index, part), seq, data)
    if live is None:
        return jsonify(text="", ramble=None)
    return jsonify(text=live["text"][-400:], ramble=delivery.ramble(live["words"], part))


@app.route("/api/answer", methods=["POST"])
def submit_answer():
    """One recorded take: the main answer (part=main) or the answer to the follow-up (part=follow_up)."""
    session_id = request.form.get("session_id")
    s = load_session(session_id)
    part = request.form.get("part", "main")
    interrupted = request.form.get("interrupted") or None
    try:
        index = int(request.form.get("index", ""))
        duration = float(request.form.get("duration", 0))
        face = json.loads(request.form.get("face") or "{}")
    except ValueError:
        return jsonify(error="Bad answer data."), 400
    if part not in ("main", "follow_up") or not 0 <= index < len(s["answers"]):
        return jsonify(error="No such question."), 400
    if interrupted not in (None, *delivery.WRAP_UP):
        return jsonify(error="Bad interruption reason."), 400
    answer = s["answers"][index]
    if part == "follow_up" and not answer.get("follow_up"):
        return jsonify(error="No follow-up was asked for that question."), 400

    face = {k: int(face.get(k, 0)) for k in ("samples", "face", "facing")}
    started = time.time()
    k = stream.key(session_id, index, part)
    result = stream.finish(k) if request.form.get("streamed") == "1" else None
    source = "live"
    if result is None:  # no live stream, or a chunk went missing: transcribe the whole recording instead
        stream.discard(k)
        audio = request.files.get("audio")
        if not audio:
            return jsonify(error="No audio was sent."), 400
        source = "full"
        try:
            result = speech.transcribe(audio.read())  # in memory; the audio is never written to disk
        except Exception as e:  # a corrupt or empty recording shouldn't kill the interview
            app.logger.exception("transcription failed")
            return jsonify(error=f"Couldn't transcribe that recording ({type(e).__name__})."), 422
    transcript, words = result
    metrics = delivery.delivery_metrics(words, duration, face)
    take = {"transcript": transcript, "words": words, "face": face, "delivery": metrics}
    if interrupted:
        take["interrupted"] = interrupted
    app.logger.info("question %d %s: %s transcript ready %.1f s after the answer ended", index + 1, part, source, time.time() - started)

    if part == "follow_up":
        update_session(session_id, lambda sess: sess["answers"][index]["follow_up"].update(take, status="answered"))
        queue_grading(session_id, index, "follow_up")
        return jsonify(transcript=transcript, delivery=metrics)

    def store(sess):
        sess["answers"][index].update(take)
        sess["answers"][index].pop("follow_up", None)  # a re-recorded answer gets a fresh follow-up
        if not interrupted:
            sess["answers"][index].pop("interrupted", None)
    update_session(session_id, store)
    queue_grading(session_id, index)  # graded now, in parallel with writing the follow-up

    asked = None
    if interrupted:  # the interviewer cut in: the wrap-up line is the follow-up, no model call needed
        asked = {"question": delivery.WRAP_UP[interrupted], "probes": "a short summary", "kind": "wrap_up"}
    elif s.get("follow_ups"):
        started = time.time()
        asked = answer_evaluator.follow_up(answer["question"], transcript, s["domain"], s["difficulty"])
        app.logger.info("question %d: follow-up %s in %.1f s", index + 1, "written" if asked else "skipped", time.time() - started)
    if asked:
        update_session(session_id, lambda sess: sess["answers"][index].update(follow_up={**asked, "status": "asked"}))
        tts_prefetch(asked["question"])
    return jsonify(transcript=transcript, delivery=metrics, follow_up={"question": asked["question"]} if asked else None)


@app.route("/api/skip-follow-up/<session_id>/<int:index>", methods=["POST"])
def skip_follow_up(session_id, index):
    s = load_session(session_id)
    f = s["answers"][index].get("follow_up") if 0 <= index < len(s["answers"]) else None
    if not f or f.get("status") != "asked":
        return jsonify(error="That question isn't waiting on a follow-up."), 400
    update_session(session_id, lambda sess: sess["answers"][index]["follow_up"].update(status="skipped"))
    return jsonify(ok=True)


@app.route("/api/finish/<session_id>", methods=["POST"])
def finish_interview(session_id):
    """Ending mid-exchange: an open follow-up counts as skipped; every answer is already graded or grading."""
    s = load_session(session_id)
    pending = [i for i, a in enumerate(s["answers"]) if (a.get("follow_up") or {}).get("status") == "asked"]
    for i in pending:
        update_session(session_id, lambda sess, i=i: sess["answers"][i]["follow_up"].update(status="skipped"))
    for i, a in enumerate(s["answers"]):
        stream.discard(stream.key(session_id, i, "main"))
        stream.discard(stream.key(session_id, i, "follow_up"))
    return jsonify(closed=len(pending))


def _warm_up_models():
    speech.load()                 # Whisper: a few seconds from the local cache
    for line in delivery.WRAP_UP.values():
        tts_prefetch(line)        # so an interruption is spoken instantly
    answer_evaluator.warm_up()    # llama-swap loads gpt-oss-20b on its first request: ~20 s warm, ~2 min cold


@app.route("/api/warmup", methods=["POST"])
def warmup():
    # The room calls this as it opens, so both models are ready by the first answer.
    threading.Thread(target=_warm_up_models, daemon=True).start()
    return jsonify(ok=True)


# Each sentence is voiced once. Two lanes: "now" (what the room is about to say: a follow-up, a cut-in,
# the current question) never waits behind "ahead" (the next question, voiced while you answer this one).
voice_now = ThreadPoolExecutor(max_workers=1)
voice_ahead = ThreadPoolExecutor(max_workers=1)
_voiced = {}
_voiced_lock = threading.Lock()


def voice_job(sentence, lane="now", voice=None):
    """The (possibly already running or finished) job voicing this sentence in the current voice."""
    v, speed = tts.current_voice()
    key = (sentence, voice or v, speed)
    with _voiced_lock:
        job = _voiced.get(key)
        if job is None or (job.done() and job.exception()):
            job = (voice_now if lane == "now" else voice_ahead).submit(tts.speak, sentence, voice or v, speed)
            _voiced[key] = job
            if len(_voiced) > 256:  # forget the oldest finished jobs; tts.speak's own cache keeps the audio
                for k in [k for k, j in _voiced.items() if j.done()][:64]:
                    del _voiced[k]
        return job


def tts_prefetch(text, lane="now"):
    if tts.available():
        for sentence in tts.sentences(text):
            voice_job(sentence, lane)


@app.route("/api/speech", methods=["POST"])
def speech_audio():
    """WAV for one sentence in the interviewer's voice (Kokoro, local). 503 means use the browser's voice."""
    body = request.get_json(silent=True) or {}
    text, voice = (body.get("text") or "").strip(), body.get("voice")
    if not text or len(text) > 600 or (voice is not None and voice not in settings.VOICES):
        return jsonify(error="Send one sentence of text (and a known voice, if any)."), 400
    if not tts.available():
        return jsonify(error="The local voice model isn't downloaded."), 503
    try:
        wav = voice_job(text, voice=voice).result(timeout=120)
    except Exception as e:
        app.logger.exception("speech failed")
        return jsonify(error=f"Couldn't voice that ({type(e).__name__})."), 503
    return app.response_class(wav, mimetype="audio/wav", headers={"Cache-Control": "private, max-age=3600"})


@app.route("/api/speech/ahead", methods=["POST"])
def speech_ahead():
    """Voice text in the background (the next question) so it plays instantly later. Returns at once."""
    text = ((request.get_json(silent=True) or {}).get("text") or "").strip()
    if text and len(text) <= 2000:
        tts_prefetch(text, lane="ahead")
    return jsonify(ok=True)


@app.route("/api/camera-check", methods=["POST"])
def camera_check():
    frame = request.files.get("frame")
    data = frame.read() if frame else b""
    if not data or len(data) > 3 * 1024 * 1024:
        return jsonify(error="Send one JPEG frame under 3 MB."), 400
    result = setup_check.check_frame(data)  # the frame is only held in memory for this call
    return jsonify(result), (502 if "error" in result else 200)


@app.route("/api/sessions")
def list_sessions():
    """Every session on this machine, newest first, with the numbers the History page shows."""
    out = []
    for name in os.listdir(SESSIONS_DIR):
        if not name.endswith(".json"):
            continue
        try:
            s = load_session(name[:-5])
        except Exception:  # a broken or foreign file shouldn't hide the rest
            continue
        summary = delivery.summarize(s.get("answers", []))
        out.append({k: s.get(k) for k in ("session_id", "company", "domain", "difficulty", "created_at", "mode")}
                   | {"questions": len(s.get("answers", [])), "summary": summary,
                      "grading": any(a.get("status") == "grading" for a in s.get("answers", []))})
    out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return jsonify(sessions=out)


@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    path = _session_path(session_id)
    with session_lock:
        os.remove(path)
    for i in range(30):  # drop any half-finished live audio for it
        stream.discard(stream.key(session_id, i, "main"))
        stream.discard(stream.key(session_id, i, "follow_up"))
    return jsonify(ok=True)


@app.route("/api/settings", methods=["GET", "POST"])
def settings_api():
    if request.method == "GET":
        return jsonify(settings.all_settings())
    try:
        saved = settings.update(request.get_json(silent=True) or {})
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(saved)


@app.route("/api/settings/test-model", methods=["POST"])
def test_model():
    """Is the grading model reachable, and does it list the chosen model?"""
    base = (request.get_json(silent=True) or {}).get("llm_base_url") or settings.get("llm_base_url")
    try:
        r = requests.get(f"{base.rstrip('/')}/models", timeout=10)
        r.raise_for_status()
        ids = [m.get("id") for m in r.json().get("data", [])]
    except Exception as e:
        return jsonify(ok=False, error=f"No answer from {base} ({type(e).__name__})."), 200
    return jsonify(ok=True, models=ids)


@app.route("/api/open-data-folder", methods=["POST"])
def open_data_folder():
    if hasattr(os, "startfile"):  # Windows: show the folder holding sessions and settings
        os.startfile(settings.DATA_DIR)
    return jsonify(ok=True)


@app.route("/api/regrade/<session_id>/<int:index>", methods=["POST"])
def regrade(session_id, index):
    s = load_session(session_id)
    part = request.args.get("part", "main")
    a = s["answers"][index] if 0 <= index < len(s["answers"]) else {}
    target = a if part == "main" else (a.get("follow_up") or {})
    if "transcript" not in target:
        return jsonify(error="Nothing to grade for that question."), 400
    queue_grading(session_id, index, part)
    return jsonify(ok=True)


@app.route("/api/report/<session_id>")
def report_data(session_id):
    s = load_session(session_id)
    return jsonify(
        session={k: s.get(k) for k in ("session_id", "company", "domain", "difficulty", "created_at", "follow_ups", "mode", "interruptions")},
        answers=s["answers"],
        summary=delivery.summarize(s["answers"]),
        ranges=delivery.RANGES,
        pause_s=delivery.PAUSE_S,
        grading=sum(a.get("status") == "grading" for a in s["answers"])
        + sum((a.get("follow_up") or {}).get("status") == "grading" for a in s["answers"]),
        voice=tts.available(),
    )


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    # threaded so the report can poll while an answer is being transcribed
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", threaded=True)
