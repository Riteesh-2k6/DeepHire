"""Grades a spoken answer's transcript with a local LLM (any OpenAI-compatible server).

Defaults to gpt-oss-20b behind llama-swap on 127.0.0.1:8080. One call returns the
model answer and the rubric scores; the weighted score is computed here, not by the model.
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

import requests
import settings


def _endpoint():
    """Where the grading model lives, from Settings (read on every call, so changes apply at once)."""
    key = settings.get("llm_api_key")  # empty for a local server
    return settings.get("llm_base_url"), ({"Authorization": f"Bearer {key}"} if key else {})

RUBRIC = {"technical_accuracy": 0.40, "problem_solving": 0.30, "completeness": 0.20, "optimization": 0.10}
CRITERIA = list(RUBRIC) + ["clarity"]  # clarity is reported under delivery, not weighted

SYSTEM_PROMPT = """You are a senior {domain} interviewer grading a {difficulty} question.
The candidate answered out loud and you are reading an automatic transcript. Ignore filler words,
false starts and transcription slips. Judge the reasoning, not code syntax or polish. If the question
asks for code, judge the approach the candidate describes.

First, in candidate_summary, say in one sentence what the candidate actually said, quoting their words.
Then set on_topic to false if their answer does not address this question at all (for example, they
answered a different question). Grade only what is in the transcript; never credit points they did not make.

Score each criterion from 0 to 10, with one sentence of justification that refers to what they said,
written to the candidate as "you":
- technical_accuracy: correctness of concepts and facts
- problem_solving: the approach, algorithm choice, complexity analysis
- completeness: covers every part of the question, including edge cases
- optimization: performance considerations and trade-offs
- clarity: how easy the explanation is to follow when heard (structure, signposting, a conclusion).
  Do not judge accent or filler words; those are measured separately.

feedback: two or three sentences on the changes that would most improve this answer, written to the
candidate as "you" (for example "Start by restating the problem...").
model_answer: last, what a strong candidate would say out loud, in about 120 words. Write your own
answer; do not repeat the candidate's.

Reply with JSON only, with exactly these keys, in this order:
{{"candidate_summary": "...", "on_topic": true, "technical_accuracy": {{"score": 0, "justification": "..."}},
"problem_solving": {{...}}, "completeness": {{...}}, "optimization": {{...}}, "clarity": {{...}},
"feedback": "...", "model_answer": "..."}}"""

OFF_TOPIC_CAP = 2.0  # an answer to a different question can't score above this on any criterion


def with_final_score(result):
    """Clamp each score to 0-10 (or the off-topic cap) and add the weighted content score.

    Raises ValueError if a criterion has no numeric score: a score the model left out must not read as 0.
    """
    ceiling = OFF_TOPIC_CAP if result.get("on_topic") is False else 10.0
    for key in CRITERIA:
        item = result.get(key)
        try:
            score = float(item["score"])
        except (TypeError, KeyError, ValueError) as e:
            raise ValueError(f"the grade has no score for {key}") from e
        result[key] = {"score": max(0.0, min(ceiling, score)), "justification": str(item.get("justification", ""))}
    result["final_score"] = round(sum(result[k]["score"] * w for k, w in RUBRIC.items()), 1)
    return result


def chat_json(messages, model=None, max_tokens=2000, timeout=900, post=requests.post):
    """One JSON-mode chat call to the local server. Raises requests.RequestException or ValueError."""
    base, headers = _endpoint()
    body = {"model": model or settings.get("llm_model"), "temperature": 0.2, "max_tokens": max_tokens, "reasoning_effort": "low",
            "response_format": {"type": "json_object"}, "messages": messages}
    r = post(f"{base}/chat/completions", json=body, headers=headers, timeout=timeout)
    r.raise_for_status()
    try:
        content = r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError("unexpected response shape") from e
    # Small models wrap JSON in ```json fences or chat around it, even in JSON mode: take the object.
    content = content or ""
    start, end = content.find("{"), content.rfind("}")
    return json.loads(content[start:end + 1] if 0 <= start < end else content)


def grade(question, transcript, domain="", difficulty="", post=requests.post):
    """Grade the main answer. Runs the moment the answer ends, while the follow-up is being written."""
    if not transcript.strip():
        return {"error": "No speech was picked up for this answer."}
    user = f"Question: {question}\n\nTranscript of the spoken answer:\n{transcript}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(domain=domain or "software", difficulty=difficulty or "medium")},
                {"role": "user", "content": user}]
    for _ in range(2):  # gpt-oss-20b now and then leaves scores out (1 in 42 answers); a second try fixes it
        try:
            return with_final_score(chat_json(messages, post=post))
        except requests.RequestException as e:
            return {"error": f"The grading model at {settings.get('llm_base_url')} didn't answer ({type(e).__name__}). Is llama-swap running?"}
        except (ValueError, AttributeError):  # not JSON, not an object, or a score missing
            pass
    return {"error": "The grading model's reply wasn't a complete grade."}


FOLLOW_UP_GRADE_PROMPT = """You are a senior {domain} interviewer. You asked the candidate a follow-up question
about their answer. You are reading automatic transcripts: ignore filler words and slips.

Score from 0 to 10 how well the follow-up answer addresses the follow-up question, given the original
question and their first answer. Grade only what they actually said. If they did not address the
follow-up at all, score 0 to 2. Write one sentence of justification to the candidate as "you".

Reply with JSON only: {{"score": 0, "justification": "..."}}"""


def grade_follow_up(question, transcript, follow_q, follow_transcript, domain="", post=requests.post):
    """A short, separate grade for the follow-up answer; the main rubric score stays as it was."""
    if not follow_transcript.strip():
        return {"error": "No speech was picked up for the follow-up."}
    messages = [{"role": "system", "content": FOLLOW_UP_GRADE_PROMPT.format(domain=domain or "software")},
                {"role": "user", "content": f"Original question: {question}\n\nTheir first answer:\n{transcript}\n\n"
                                            f"Your follow-up: {follow_q}\n\nTheir follow-up answer:\n{follow_transcript}"}]
    try:
        result = chat_json(messages, max_tokens=600, post=post)
        score = max(0.0, min(10.0, float(result.get("score", 0))))
    except requests.RequestException as e:
        return {"error": f"The grading model at {settings.get('llm_base_url')} didn't answer ({type(e).__name__})."}
    except (ValueError, TypeError, AttributeError):
        return {"error": "The grading model returned something that wasn't the expected JSON."}
    return {"score": score, "justification": str(result.get("justification", ""))}


# A socket timeout only fires when no bytes arrive; a server that trickles bytes (say, while a model
# loads) can outlast it. Calls with a hard deadline run here and are abandoned, not killed, when late.
# ponytail: two workers; an abandoned call holds one until the server answers or its socket times out.
_deadline_pool = ThreadPoolExecutor(max_workers=2)


def within(seconds, fn, *args, **kwargs):
    """fn(*args, **kwargs), or None if it takes longer than `seconds`. Exceptions pass through."""
    try:
        return _deadline_pool.submit(fn, *args, **kwargs).result(timeout=seconds)
    except FuturesTimeout:
        return None


def warm_up(post=requests.post):
    """A one-token request: llama-swap loads the model on first use, so this pays that cost early."""
    try:
        base, headers = _endpoint()
        post(f"{base}/chat/completions", timeout=300, headers=headers,
             json={"model": settings.get("llm_model"), "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1})
    except requests.RequestException:
        pass


FOLLOW_UP_TIMEOUT_S = float(os.getenv("FOLLOW_UP_TIMEOUT_S", "45"))  # past this, the interview moves on

FOLLOW_UP_PROMPT = """You are a senior {domain} interviewer in a live {difficulty} interview. The candidate
just answered out loud; you are reading an automatic transcript, so ignore filler words and slips.

Ask exactly ONE follow-up question of at most 30 words, the one a good interviewer would ask next:
probe the most important gap, a vague claim, a missing edge case, or a trade-off they skipped.
Refer to something they actually said. If they did not address the question, ask them to come back to it.
Never ask two questions, and never give feedback, hints or the answer.

Reply with JSON only: {{"follow_up": "...", "probes": "a few words naming what it tests"}}"""


def clean_follow_up(text, main_question):
    """One short question or None: keeps the first question, adds a missing '?', drops echoes and essays."""
    text = re.sub(r"\s+", " ", str(text or "")).strip().strip('"')
    if "?" in text:
        text = text[: text.index("?") + 1]
    elif text:
        text += "?"
    same = lambda t: t.strip().lower().rstrip("?.! ")
    if not 8 <= len(text) <= 300 or same(text) == same(main_question):
        return None
    return text


def follow_up(question, transcript, domain="", difficulty="", post=requests.post, timeout=None):
    """The interviewer's follow-up as {"question", "probes"}, or None if there shouldn't be one."""
    if len(transcript.split()) < 3:
        return None  # nothing said: no follow-up, just grade the silence
    messages = [{"role": "system", "content": FOLLOW_UP_PROMPT.format(domain=domain or "software", difficulty=difficulty or "medium")},
                {"role": "user", "content": f"Question: {question}\n\nTranscript of the spoken answer:\n{transcript}"}]
    deadline = timeout or FOLLOW_UP_TIMEOUT_S
    try:
        result = within(deadline, chat_json, messages, max_tokens=400, timeout=deadline, post=post)
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(result, dict):
        return None  # late or malformed: the interview moves on without a follow-up
    q = clean_follow_up(result.get("follow_up"), question)
    return {"question": q, "probes": str(result.get("probes", ""))[:120]} if q else None
