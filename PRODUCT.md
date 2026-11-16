# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary:** final-year computer-science students rehearsing technical interviews alone, on their own laptop, before placement and internship rounds. They want to hear a question, answer it out loud on camera, and find out what to fix.
- **Secondary:** recruiters and hiring managers who see DeepHire as its author's portfolio project. They need to understand what it does and how honest it is within a glance at any page.

## Product Purpose

A self-practice video mock interviewer. An AI interviewer reads each question aloud; the student answers on camera and microphone; afterwards one report shows what they said (content graded against a rubric) next to how they said it (pace, pauses, filler words, facing the camera), with their own recording to replay. Success is a student who can name the two or three concrete things to change before the next attempt.

## Positioning

It runs entirely on the student's own machine: questions are spoken by the browser, speech is transcribed by a local Whisper model, answers are graded by a local LLM, and face tracking runs in the browser. Nothing is uploaded. It measures only behaviour the student can see and change, and refuses to infer emotion or "confidence" from faces (the science doesn't support it and the EU AI Act restricts it in hiring and education).

## Operating Context

- Flow: setup (company, domain, difficulty, number of questions) → consent, camera/mic check, 3-second calibration → interview room → report.
- A session is 3, 5 or 10 questions; spoken answers run 1–3 minutes each, up to a 3-minute cap.
- Grading by the local LLM takes about 30 s to a few minutes per answer and runs in the background while the student keeps answering, so the report fills in progressively.
- Used at a desk with the camera on, often in a dim room, where the screen itself lights the student's face.

## Capabilities and Constraints

- Flask + Jinja templates, plain JavaScript (ES modules), no build step. Everything must work offline after a one-time setup: no CDN fonts or scripts at runtime; vendored files live in `deephire/static/vendor/`.
- Question bank: 990 questions in SQLite, tagged by company (Google, Meta, Amazon, Apple, Infosys, Capgemini; Netflix has none), domain (7) and difficulty (3). 419 are coding questions answered as "talk me through your approach".
- Content rubric: technical accuracy 40%, problem solving 30%, completeness 20%, optimization 10%; plus a separate clarity score reported with delivery.
- Delivery signals: words per minute, pauses of 2 s or more, time before the first word, filler words per minute (a lower bound), share of time facing the camera, share of time the face is in frame. No composite delivery or confidence score.
- Video recordings stay in the browser (IndexedDB) for replay; audio is transcribed in memory by the local server and never saved.
- Undecided: adaptive follow-up questions (M2), a code pad (M3), the landing page redesign (M3).

## Brand Commitments

- The name **DeepHire** is kept. The current logo, colours and fonts are not binding and may be replaced.
- The interview must never feel like being watched or judged (no recording-light theatrics, no live scores while answering, no proctoring language), never like a cold exam portal, and never use a fake human avatar for the interviewer.

## Evidence on Hand

- Real: the question bank, the rubric, and measured local performance (Whisper base transcribes 13.4 s of speech in 1.3 s on CPU).
- Absent: no real users, testimonials, outcomes or accuracy studies. The landing page's testimonials are placeholders and must not be presented as real. LLM scores have not been validated against human graders and the product says so.

## Product Principles

1. Measure what the student can change; never claim to read their mind.
2. The student's video and voice stay on their machine.
3. Say what a number means and how sure it is, next to the number.
4. Practice should feel like a calm rehearsal room, not an exam hall or a surveillance feed.
5. A recruiter skimming any page should see both what it does and where its limits are.

## Accessibility & Inclusion

- Every spoken question is also shown as text (deaf and hard-of-hearing students, noisy rooms, accents).
- Delivery feedback must not penalise accent, stammering or neurodivergent expression; fillers and pauses are shown as facts with rules-of-thumb ranges, not as grades.
- Works without a camera (audio-only, with face signals marked unavailable).
