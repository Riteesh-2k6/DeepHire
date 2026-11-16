# DeepHire

**AI mock interviews for a specific company, role and difficulty, with every answer scored and explained.**

Practice question lists tell you what might be asked but not how good your answer was. DeepHire runs a short technical interview in a chat window, then has a language model grade each answer against a model answer, using a fixed rubric, so you see where you lost marks.

## How it works

1. **Pick the interview.** Company (Google, Meta, Amazon, Apple, Infosys, Capgemini), domain (Full Stack, Front End, Back End, Java, Python, AI/ML, System Design) and difficulty (Easy, Medium, Hard).
2. **Get 10 questions.** They come from a SQLite bank of 990 questions tagged by company, domain and difficulty. Between 1 and 6 are at your chosen difficulty and the rest are from the other levels, shuffled, so no two sessions match.
3. **Answer in a chat.** The interview runs as a conversation, one question at a time. You can end early.
4. **Get scored per answer.** For each answer, Llama 3 (on Groq) first writes a model answer, then grades yours on four weighted criteria:

   | Criterion | Weight |
   |---|---|
   | Technical accuracy | 40% |
   | Problem solving | 30% |
   | Completeness | 20% |
   | Optimization | 10% |

   You get a 0–10 score per criterion with a reason, a weighted final score, and two or three sentences on what to improve.
5. **Review.** Download your responses as JSON. The separate **Answer Evaluator** (`ans_eval/`) takes that file and produces a full report with the model answers side by side.

The site also has nine short articles on interview preparation.

## Run it

Requires Python 3.10+ and a [Groq API key](https://console.groq.com/keys).

```bash
pip install -r requirements.txt
cp .env.example .env        # then put your key in .env
cd deephire
python app.py               # http://127.0.0.1:5000
```

The Answer Evaluator runs on its own: `cd ans_eval && python flask-app.py` (it reads `GROQ_API_KEYS`, a comma-separated list).

## Layout

```
deephire/              main app (Flask)
  app.py               routes: pages, interview setup, chat, evaluation
  smar_selector.py     picks 10 questions from interview_questions.db
  answer_evaluator.py  model answer + rubric scoring via Groq
  templates/           landing page, interview setup, chat, results, blog
ans_eval/              standalone evaluator for a downloaded responses file
```

## Stack

Python, Flask, SQLite, Groq API (Llama 3), HTML/CSS/JavaScript.

## Status

A prototype built in 2025. Known gaps:
- Netflix appears in the company list but has no questions in the bank yet, and Meta has 45 against 189 for the others.
- Scores come from a single model call per answer and haven't been checked against human graders.
