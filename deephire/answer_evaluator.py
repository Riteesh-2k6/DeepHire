"""Grades a spoken answer's transcript with a local LLM (any OpenAI-compatible server).

Defaults to gpt-oss-20b behind llama-swap on 127.0.0.1:8080. One call returns the
model answer and the rubric scores; the weighted score is computed here, not by the model.
"""
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-oss-20b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")  # empty for a local server

RUBRIC = {"technical_accuracy": 0.40, "problem_solving": 0.30, "completeness": 0.20, "optimization": 0.10}
CRITERIA = list(RUBRIC) + ["clarity"]  # clarity is reported under delivery, not weighted

SYSTEM_PROMPT = """You are a senior {domain} interviewer grading a {difficulty} question.
The candidate answered out loud and you are reading an automatic transcript. Ignore filler words,
false starts and transcription slips. Judge the reasoning, not code syntax or polish. If the question
asks for code, judge the approach the candidate describes.

First, in candidate_summary, say in one sentence what the candidate actually said, quoting their words.
Then set on_topic to false if their answer does not address this question at all (for example, they
answered a different question). Grade only what is in the transcript; never credit points they did not make.

Score each criterion from 0 to 10, with one sentence of justification that refers to what they said:
- technical_accuracy: correctness of concepts and facts
- problem_solving: the approach, algorithm choice, complexity analysis
- completeness: covers every part of the question, including edge cases
- optimization: performance considerations and trade-offs
- clarity: how easy the explanation is to follow when heard (structure, signposting, a conclusion).
  Do not judge accent or filler words; those are measured separately.

feedback: two or three sentences on the changes that would most improve this answer.
model_answer: last, what a strong candidate would say out loud, in about 120 words. Write your own
answer; do not repeat the candidate's.

Reply with JSON only, with exactly these keys, in this order:
{{"candidate_summary": "...", "on_topic": true, "technical_accuracy": {{"score": 0, "justification": "..."}},
"problem_solving": {{...}}, "completeness": {{...}}, "optimization": {{...}}, "clarity": {{...}},
"feedback": "...", "model_answer": "..."}}"""

OFF_TOPIC_CAP = 2.0  # an answer to a different question can't score above this on any criterion


def with_final_score(result):
    """Clamp each score to 0-10 (or the off-topic cap) and add the weighted content score."""
    ceiling = OFF_TOPIC_CAP if result.get("on_topic") is False else 10.0
    for key in CRITERIA:
        item = result.get(key) or {}
        try:
            score = float(item.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        result[key] = {"score": max(0.0, min(ceiling, score)), "justification": str(item.get("justification", ""))}
    result["final_score"] = round(sum(result[k]["score"] * w for k, w in RUBRIC.items()), 1)
    return result


def grade(question, transcript, domain="", difficulty="", post=requests.post):
    if not transcript.strip():
        return {"error": "No speech was picked up for this answer."}
    body = {
        "model": LLM_MODEL,
        "temperature": 0.2,
        "max_tokens": 2000,
        "reasoning_effort": "low",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.format(domain=domain or "software", difficulty=difficulty or "medium")},
            {"role": "user", "content": f"Question: {question}\n\nTranscript of the spoken answer:\n{transcript}"},
        ],
    }
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
    try:
        r = post(f"{LLM_BASE_URL}/chat/completions", json=body, headers=headers, timeout=900)
        r.raise_for_status()
        result = json.loads(r.json()["choices"][0]["message"]["content"])
    except requests.RequestException as e:
        return {"error": f"The grading model at {LLM_BASE_URL} didn't answer ({type(e).__name__}). Is llama-swap running?"}
    except (KeyError, IndexError, ValueError):
        return {"error": "The grading model returned something that wasn't the expected JSON."}
    return with_final_score(result)
