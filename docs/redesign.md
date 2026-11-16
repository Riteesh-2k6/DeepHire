# DeepHire redesign: a video AI interviewer for self-practice

Status: **approved 16 Nov 2026 (option A, everything local). M1 built.**
Rev 2 (16 Nov 2026): everything runs on your own machine, with no cloud API calls. A note on VLMs is added.
Visual direction (chosen 16 Nov): "Recording Session". Each answer is a take in a bright booth, the interviewer is a talkback meter, and the report is a track sheet. Product context is in [PRODUCT.md](../PRODUCT.md).

## 1. What we're building, and why

DeepHire today is a text chat: ten questions from a 990-question bank, each typed answer graded by an LLM on a fixed rubric. Real interviews are spoken, on camera, under time pressure. The typed version skips half of the skill.

The redesign turns it into a **video interview you run on yourself, entirely on your own machine**. An AI interviewer asks each question out loud. You answer on camera and microphone. Afterwards you get one report that puts **what you said** (content, graded against a rubric) next to **how you said it** (delivery: pace, pauses, filler words, whether you faced the camera), with your own recording to replay.

It is a practice tool, not a hiring tool. The candidate is the only user and the only person who sees the results.

## 2. What HackerRank's Chakra actually does (checked 16 Nov 2026)

Chakra went GA on 5 Oct 2026, after a beta HackerRank puts at 500,000+ interviews ([TechCrunch](https://techcrunch.com/2026/10/05/hackerranks-ai-interviewer-offers-a-glimpse-into-what-job-interviews-could-become/)). From HackerRank's own pages ([intro](https://hackerrank-knowledge-base.help.usepylon.com/articles/6908366644), [how it works](https://www.hackerrank.com/writing/how-does-an-ai-interviewer-work), [July 2026 release notes](https://support.hackerrank.com/articles/8142080826-july-2026-release-notes), [YC launch](https://www.ycombinator.com/launches/PQb-chakra-ai-interviewer-that-finally-works)):

- **Format:** structured voice/video screening interviews. Follow-up questions adapt to each answer. Coding questions get an in-line editor, and Chakra then asks about the approach.
- **Scoring:** against the employer's rubric (technical accuracy, depth, communication clarity, problem-solving), with transcript excerpts as evidence.
- **Report:** overall and section scores, strengths, gaps, transcript, highlighted excerpts, and full session replay (webcam, screen and transcript together).
- **Status:** the UI shows its status ("Listening", "Thinking") throughout.
- **Integrity:** it flags extra monitors, screen sharing and leaving full screen, and pauses the interview.
- **What it does not claim:** none of those pages says Chakra infers emotion or confidence from facial expressions. Its "communication" score is about how clearly reasoning is explained, judged from the content.

**What we take:** spoken questions, a visible interviewer status, follow-up questions, transcript-backed scoring, session replay.
**What we leave out:** proctoring. You can't cheat yourself, and a practice tool shouldn't watch you that way.

## 3. The decision before building: what "confidence" means here

You asked for live micro-expression reading to judge confidence. I recommend **not** doing that, and measuring observable behaviour instead.

**Why not facial emotion or confidence inference:**

1. **The science doesn't hold up.** The major review of the evidence found that facial movements don't reliably map to inner states across people and contexts (Barrett et al., 2019, *Psychological Science in the Public Interest*, "Emotional Expressions Reconsidered"). Micro-expressions specifically are rare. In the main study of how often they occur, about 2% of 697 expressions were micro-expressions, shown by about 22% of people ([Porter & ten Brinke 2008](https://www.psychologicalscience.org/journals/psychological-science/j.1467-9280.2008.02116.x/)). Even when one appears, it doesn't say why.
2. **It is restricted where this would be used.** The EU AI Act, Article 5(1)(f), bans AI that infers emotions in workplaces and education institutions. The Commission's guidelines name emotion recognition during recruitment as an example ([FPF summary](https://fpf.org/blog/red-lines-under-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/)). Illinois' AI Video Interview Act adds notice and consent rules for AI analysis of applicant video.
3. **It's the wrong signal for a portfolio.** For an AI product role, a project that knows where the evidence stops reads better than one that overclaims.

**And a VLM doesn't change that.**

- **It can't see micro-expressions.** They last under about half a second: CASME II, the standard research set, was filmed at 200 fps and its clips average about 0.33 s ([CASME II](https://pmc.ncbi.nlm.nih.gov/articles/PMC3903513/)). Video VLMs typically sample about 1 frame per second ([Gemini video docs](https://ai.google.dev/gemini-api/docs/generate-content/video-understanding)), and a single frame can't separate a fleeting expression from an ordinary one.
- **It always answers fluently,** whether or not there is anything real to read.
- **The law doesn't care which kind of model does it.** A VLM inferring emotion is still emotion inference.

**Where a VLM does help** is describing the scene, not the person's feelings: lighting, framing, camera angle, background. That is in M2 as an opt-in camera check.

**What we measure instead.** Each of these is a behaviour you can see and change, reported in plain units with a reference range:

| Signal | How it's measured | Where it runs |
|---|---|---|
| Speaking pace (words/min) | Word timestamps from the local transcript | Local server |
| Pauses | Gaps of 2 s or more between words: count and longest | Local server |
| Time before you start | First word's timestamp | Local server |
| Filler words per minute | "um", "uh", "er", "hmm" and similar in the transcript. A lower bound (see 5.3) | Local server |
| Looking at the camera | Head and eye direction compared with your own calibration | Browser, on-device |
| Face in frame | Whether the face tracker finds a face | Browser, on-device |
| Content: rubric scores | Local LLM grades the transcript | Local server + local LLM |
| Clarity of the explanation | Local LLM rates how easy the answer is to follow when heard | Local server + local LLM |

There is no single "confidence score". The report says "you paused 6 times for 3 s or more" and "you faced the camera 71% of the time", not "you seemed nervous". Facial blendshapes (smile, brow raise and so on) are never turned into emotion labels.

**Options for you to choose from:**

- **A. Observable behaviour only (recommended).** The table above, no composite score. Plus the opt-in VLM camera check in M2.
- **B. A plus a "delivery" summary score.** A weighted blend of the same signals, labelled as a practice heuristic, never as confidence. Easier to compare sessions, but it invents weights we can't validate.
- **C. Facial expression to emotion/confidence, as first asked.** Not recommended, for the reasons above.

## 4. User flow

1. **Setup** (the existing page, restyled): company, domain, difficulty, and a new **number of questions** (3, 5 or 10; default 5, since spoken answers take 1–3 minutes each).
2. **Before you start:** one screen that says what is captured and that none of it leaves your machine. It also runs a camera and microphone check and a 3-second calibration ("look at the camera"). Start stays disabled until you tick consent.
3. **The interview room:**
   - **Interviewer panel:** an abstract voice indicator, not a fake human face, with a status label (Speaking, Listening, Thinking).
   - **What you see:** your self-view, the question as a caption you can re-read, and a timer.
   - **Answering:** the interviewer reads the question aloud and recording starts when it finishes. You click **Done answering**, or recording stops at 3 minutes. Skip and End interview are always available.
   - **Live strip:** a small strip you can hide, showing whether you're looking at the camera now, your talking time, and a silence timer. It's meant to nudge you without pulling you out of the answer.
   - **Grading:** transcription and grading run in the background while you move on.
4. **Report:**
   - **Top:** content score (weighted rubric average) and delivery facts in plain words.
   - **Per question:** the question, your transcript with pauses and fillers marked, rubric scores with reasons, the improvement note, the model answer (collapsed), delivery numbers against their reference ranges, and your video replay.
   - **Updates in place:** the page fills in as grading finishes, with no reloads.

## 5. Architecture

Everything below runs on your machine. The only network use is the one-time download of open models and libraries during setup.

```
Browser                                           Flask server (localhost)          Local models
───────                                           ────────────────────────          ────────────
getUserMedia (camera + mic)
 ├─ MediaRecorder: video+audio ─► IndexedDB (replay)
 ├─ MediaRecorder: audio only  ─► POST /api/answer ─► faster-whisper ─────────────► Whisper base (CPU)
 ├─ MediaPipe Face Landmarker (WASM, ~5 fps)          │  word timestamps
 │    head + eye direction vs calibration             ├─ delivery metrics (pure Python)
 │    ─► per-answer counts, no images ─► POST          ├─ grading queue (background) ─► gpt-oss-20b via llama-swap
 └─ Web Audio: voice activity (live strip)            └─ sessions/<id>.json                (127.0.0.1:8080)
speechSynthesis (local OS voices only): reads questions aloud
GET /api/report/<id> ◄── report page polls until grading is done
```

### 5.1 Why each piece

- **Questions spoken by `speechSynthesis`.**
  - It's built into the browser, so no new dependency.
  - Some browser voices are cloud voices: Chrome's "Google" voices and Edge's "Online (Natural)" voices. So we only use voices the browser marks `localService`; on Windows those are the built-in Microsoft voices.
- **Face tracking with MediaPipe Face Landmarker.**
  - It runs in the browser via WebAssembly. Its files (library, WASM, `face_landmarker.task` model) are downloaded once into `static/vendor/` by a setup script and served by Flask. No CDN at runtime.
  - Per frame we keep two flags: face found, and looking at the camera. Images and landmarks are never kept.
- **"Looking at the camera" against your own baseline.**
  - Calibration records your head's forward direction and eye blendshapes.
  - A frame counts as "looking at camera" when the head is within 20° of that baseline and the eyes haven't moved far from theirs.
  - Both thresholds are named constants that can be tuned.
- **Transcription with faster-whisper on the local server.**
  - Model `base` on CPU, int8. It gives word-level timestamps, which pace, pauses and fillers all come from.
  - **Measured on this laptop:** 13.4 s of speech transcribed in 1.3 s, model load 1.6 s. The `base` model was already in your Hugging Face cache.
  - `WHISPER_MODEL=small` trades speed for accuracy.
  - Needs Python 3.12 (in `.venv`) and `av<16`: PyAV 19 breaks faster-whisper 1.2.1's audio decoding.
- **Grading with your local gpt-oss-20b, served by llama-swap at `127.0.0.1:8080`.**
  - llama-swap is already set up to start at login.
  - It speaks the OpenAI chat API, so the code is a plain HTTP call. `LLM_BASE_URL` and `LLM_MODEL` can point it at another local model, or at a hosted one later, without code changes.
  - One call per answer returns the model answer and the rubric scores together. Today it's two calls, so this halves the time.
  - JSON mode works: I tested `response_format: json_object` with `reasoning_effort: low`.
  - The rubric and its weights stay (40/30/20/10).
  - Two prompt changes: the answer is a spoken transcript, so judge the reasoning rather than code syntax or polish; and return one extra field, `clarity` (0–10), reported under delivery and not mixed into the content score.
  - The current code's `llama3-8b-8192` on Groq was shut down in Aug 2025, so grading is broken today anyway.
- **Metrics in plain Python, tested.**
  - Pace, pauses and fillers are pure functions of the word list, covered by unit tests.
  - The LLM call and Whisper are stubbed in tests.
- **Storage stays as JSON files** in `sessions/`, as today.

### 5.2 Coding questions

419 of the 990 questions ask you to write code ("Write a Python function that…"), and saying code out loud is awkward.

- **In M1:** the interviewer frames these as "talk me through how you'd solve this", the caption shows the full question, and the grader judges the approach, not syntax.
- **In M3:** a code pad next to the video, as Chakra has.

### 5.3 Known limits, stated in the report

- **Grading speed depends on your GPU being free.**
  - Your llama-swap notes measured about 12.7 tokens/s writing. A graded answer is about 350 tokens, so roughly 30 s.
  - When I tested today, another llama-server was also loaded, and RAM and VRAM were nearly full. Under that contention I measured 2.6 tokens/s, about 2.5 minutes per answer.
  - Grading runs one answer at a time in the background while you keep answering. So the wait at the end is roughly the last answer's grading, not all of them.
- **A 20B local model grades less reliably than a large hosted one.** The scores haven't been checked against human graders, and the report says so.
- **Fillers are undercounted.** Whisper tends to tidy up disfluencies. We prompt it with filler-heavy text to keep them; in my test "Um" and "Uh" survived. The count is still a lower bound and is labelled that way.
- **Pace ranges are rules of thumb.** About 120–160 words a minute is a common guide for clear speech, not a measured standard.
- **Head and eye direction is approximate.** Glasses, low light and a camera far to the side reduce accuracy. Calibration handles most camera placements.

## 6. Models

| Job | Model | Runs on | Setting |
|---|---|---|---|
| Reading questions aloud | OS voices (`localService`) | Browser | none |
| Face and eye direction | MediaPipe Face Landmarker | Browser (WASM) | thresholds in JS |
| Transcription | faster-whisper `base` | CPU | `WHISPER_MODEL` |
| Grading | gpt-oss-20b (llama-swap) | GPU + CPU | `LLM_BASE_URL`, `LLM_MODEL` |

## 7. Privacy

- **Nothing leaves your machine.**
  - Video stays in the browser's own storage (IndexedDB) for replay, and can be downloaded or deleted from the report.
  - Each answer's audio goes only to the local Flask server, which transcribes it in memory and never writes it to disk.
  - The transcript goes only to the local LLM.
- **Consent first.** Nothing is captured until you tick a consent box that says exactly this. You can stop at any time.
- **What's saved on disk** is `sessions/<id>.json`: transcripts, scores and per-answer counts (frames with a face, frames looking at the camera). No images, landmarks or audio.

## 8. Milestones

**M1: video interview room (this approval).**
- Number of questions on the setup page.
- Consent, device check and calibration.
- Spoken questions with Speaking/Listening/Thinking status, and recording per answer.
- On-device face signals and the live strip.
- Local transcription and delivery metrics.
- Background grading on the local LLM with the new prompt.
- Report page with content and delivery side by side, plus video replay.
- A setup script that downloads the MediaPipe files once.
- Tests: unit tests for the metrics and the answer endpoint (models stubbed), and a browser run with Chromium's fake camera and microphone.
- Committed locally.

**M2: a real interviewer.**
- One adaptive follow-up per question, generated by the local LLM from your answer.
- A per-answer quick take between questions in "practice" mode, and a "mock" mode that saves feedback for the end.
- The opt-in VLM camera check: lighting, framing, eye line and background, from one frame, never emotions. This needs a local vision model (for example a small Gemma or Qwen-VL GGUF with its `mmproj` file, about 3 GB) added to llama-swap.

*M2 build notes (16 Nov 2026).*

- **Follow-up questions:**
  - Right after a main answer is transcribed, the local LLM writes one follow-up of 30 words or fewer that probes the weakest or vaguest part of the answer.
  - The interviewer shows "Thinking" while it writes. It has a 45 s deadline; past that, or on any failure, the interview simply moves on.
  - The rubric grades the whole exchange (main answer plus follow-up answer), so each question still gets one score.
  - Follow-ups can be switched off on the setup page.
- **Practice and mock mode:**
  - Mock (the default) holds all feedback for the report, like a real interview.
  - Practice shows a quick take after each question: delivery facts at once, and the content score when grading finishes. You move on when ready.
- **Camera check:**
  - At the sound check, one still frame goes to a local vision model: Qwen2.5-VL-3B, about 2.8 GB. It returns two to four setup tips on lighting, framing, camera height and background.
  - The prompt forbids comments on the person, and a word filter in code drops any line about emotions or appearance. The frame is never stored.
  - The model runs on the CPU, in a llama-swap group with `swap: false`, so it runs beside gpt-oss-20b instead of swapping it out. Swapping hung once on this laptop: llama-swap got stuck "stopping" gpt-oss-20b and every request queued behind it.
  - A check takes about a minute while the model loads, then about 5 s.
  - **Tip quality is mixed and unverified on a real face.** It was tested on a synthetic frame with no person in it. It named the bright window, but sometimes gave contradictory advice. The room labels the tips as suggestions from a small model that can be wrong.
- **What testing changed** (a fake camera and microphone, on a laptop busy with other jobs):
  - The follow-up 45 s limit is now a wall-clock deadline. A socket timeout alone can be outlasted by a server that trickles bytes while it loads a model.
  - The room warms up Whisper and gpt-oss-20b as soon as it opens, so the first answer doesn't wait on a cold load of about 2 minutes.
  - Whisper runs with 4 threads (`WHISPER_THREADS`). With one thread per core, 13 s of speech took about 50 s when other programs held some cores; with 4 threads it took about 16 s, and about 1–2 s on an idle machine.
  - Whisper loads from the local cache only. faster-whisper had been checking Hugging Face for a newer model version on every start.
  - Robustness fixes:
    - A camera that stops mid-session switches the room to "no camera numbers" instead of crashing calibration.
    - A recorder that stops on its own no longer freezes the room.
    - Session files are read under the same lock as writes: on Windows, `os.replace` fails while another thread has the file open.

**M3: coding and the front door.**
- A code pad for coding questions.
- Landing page redesign, removing the placeholder testimonials or replacing them with real ones.
- Session history on the device, so you can see whether you're improving.

**M4: trust.**
- Fill the question-bank gaps (Netflix has 0 questions, Meta 45).
- Grade 30–50 answers by hand, compare them with the local LLM's scores, and publish the agreement in the README.
- Optional hosted models for people without a GPU, through the same `LLM_BASE_URL` setting.

All page design (setup, room, report, and later the landing page) is done with the `/impeccable` design skill.

## 9. Decisions

1. **Signals:** option A, observable behaviour only. Decided 16 Nov 2026.
2. **Everything local, no API calls.** Decided 16 Nov 2026. llama-swap has to be running, as it is after login.
