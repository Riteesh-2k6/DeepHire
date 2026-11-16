# DeepHire

**Practise technical interviews out loud, on camera, entirely on your own computer.**

An AI interviewer reads each question aloud. You answer on camera and microphone. Afterwards you get a track sheet that puts **what you said** (graded against a rubric) next to **how you said it** (pace, pauses, filler words, time facing the camera), with every word on a timeline and your own recording to replay.

Nothing is uploaded. Questions are spoken by your operating system's voice, speech is transcribed by a local Whisper model, answers are graded by a local LLM, and face tracking runs inside the browser.

## How it works

1. **Book a session.** Company (Google, Meta, Amazon, Apple, Infosys, Capgemini), domain (Full Stack, Front End, Back End, Java, Python, AI/ML, System Design), difficulty, and 3, 5 or 10 questions from a bank of 990.
2. **Sound check.** Consent, camera and microphone, then three seconds looking into the lens. That calibration is your own baseline for "looking at the camera", so it works wherever your webcam sits.
3. **The interview.** Each question is read aloud and shown on screen. Recording starts when it finishes; you click *Done answering* (or it stops at 3 minutes). A small console shows your mic level, whether you're facing the camera, talking time and the current silence. You can hide it.
4. **The track sheet.** While you keep answering, each take is transcribed (faster-whisper, word timestamps) and graded in the background by a local LLM. The report shows:
   - every take as a lane of words over time, with fillers and pauses of 2 s or more marked;
   - content scores per criterion with reasons, a weighted score, what to change, and a strong answer for comparison;
   - delivery facts with rule-of-thumb ranges: words per minute, pauses, time before the first word, fillers per minute, share of time facing the camera;
   - your video, replayed from the browser that recorded it.

| Content criterion | Weight |
|---|---|
| Technical accuracy | 40% |
| Problem solving | 30% |
| Completeness | 20% |
| Optimization | 10% |

Clarity (how easy the answer is to follow when heard) is scored too, but reported with delivery and not weighted into the content score.

## What it deliberately doesn't do

It never infers emotion or "confidence" from your face. Facial expressions don't reliably map to inner states (Barrett et al., 2019), and the EU AI Act bans emotion recognition in workplaces and education, including recruitment. DeepHire measures behaviour you can see and change instead. The full reasoning is in [docs/redesign.md](docs/redesign.md).

## Run it

Needs Python 3.12 (faster-whisper's dependencies don't support 3.14 yet), a webcam and microphone, and Chrome or Edge.

```bash
python -m venv .venv            # or: uv venv --python 3.12 .venv
.venv\Scripts\activate          # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt
python scripts/fetch_vendor.py  # one-time: MediaPipe face tracking and the UI font
python deephire/app.py          # http://127.0.0.1:5000
```

**Grading needs a local LLM** behind an OpenAI-compatible endpoint. The default is `gpt-oss-20b` at `http://127.0.0.1:8080/v1` (llama-swap or `llama-server`). Point it elsewhere with `LLM_BASE_URL` and `LLM_MODEL` in a `.env` file (see `.env.example`). If the model isn't reachable, the report says so and offers *Grade again* once it is.

The first transcription downloads the Whisper `base` model (about 140 MB) into your Hugging Face cache. `WHISPER_MODEL=small` is more accurate and slower.

Tests: `pytest` (the models are stubbed).

## Privacy

- **Video** stays in the browser's IndexedDB for replay. You can download or delete each take from the report.
- **Audio** goes only to the local Flask server, which transcribes it in memory and never writes it to disk.
- **Saved on disk:** `deephire/sessions/<id>.json`, holding transcripts, word timings, scores and per-answer frame counts (frames with a face, frames facing the camera). No images, face landmarks or audio. The folder is git-ignored.

## Known limits

- Content scores come from one local-model call per answer and haven't been checked against human graders. A 20B local model grades less reliably than a large hosted one.
- Grading takes about 30 s per answer on an RTX 3050 when the GPU is free, and minutes when it's busy. The report fills in as answers finish.
- Speech recognition tidies away some "um"s and "uh"s, so filler counts are a lower bound.
- Facing the camera is estimated from head and eye direction. Glasses, low light and a camera far to one side reduce accuracy.
- 419 of the 990 questions ask for code. For now you talk through the approach; a code pad is planned.
- Netflix has no questions in the bank, so it isn't offered, and Meta has 45 against 189 for the others.

## Layout

```
deephire/
  app.py               routes: setup, room, report, answer upload, grading queue
  delivery.py          pace, pauses, fillers, camera share (pure functions)
  speech.py            local transcription (faster-whisper)
  answer_evaluator.py  rubric grading via a local OpenAI-compatible LLM
  smar_selector.py     picks questions from interview_questions.db
  templates/           setup, room, report (+ the landing page and blog)
  static/js/           room logic, face tracking, recording, report
scripts/fetch_vendor.py  downloads the offline browser files
tests/                 delivery metrics, grading, API flow
docs/redesign.md       design doc: Chakra research, signal choices, milestones
ans_eval/              older standalone evaluator for exported chat sessions (uses Groq)
```

## Status

M1 of the redesign is built: the video room, spoken questions, local transcription and grading, and the track-sheet report. Next is M2: adaptive follow-up questions and an opt-in camera-setup check from a local vision model. The landing page still describes the old text-chat version, and its testimonials are placeholders, not real users; it's rebuilt in M3.
