"""How often does the local grader agree with a human? The M4 "trust" check (slow; not run by pytest).

    python scripts/grader_agreement.py            # grade new cases with the local model, then report
    python scripts/grader_agreement.py --by-hand  # grade the cases yourself, one at a time
    python scripts/grader_agreement.py --report   # report from what's already graded (no model calls)

The cases (eval/grader_agreement/cases.json) are saved interview transcripts plus synthetic ones, each
labelled good, partial, weak, off_topic or empty. Human scores go in human_grades.csv, by hand or with
--by-hand. Model scores are cached in model_grades.json per grader version, which is a hash of
answer_evaluator.py and the model name. An interrupted run resumes; a prompt change grades everything
again and keeps the old run. The report is printed and written to results.md.
"""
import csv
import hashlib
import inspect
import json
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deephire"))
import answer_evaluator  # noqa: E402
import settings  # noqa: E402

DIR = ROOT / "eval" / "grader_agreement"
CASES = json.loads((DIR / "cases.json").read_text(encoding="utf-8"))
HUMAN, MODEL, RESULTS = DIR / "human_grades.csv", DIR / "model_grades.json", DIR / "results.md"
KINDS = ["good", "partial", "weak", "off_topic", "empty"]
HIGH = 3  # an off-topic or empty answer scoring above this is a grader failure (the bar grade_check.py uses)
BANDS = [(0, 2), (3, 4), (5, 6), (7, 8), (9, 10)]
HOW_TO_GRADE = """Give each answer one content score from 0 to 10, as the rubric would weight it:
technical accuracy 40%, problem solving 30%, completeness 20%, optimization 10%.
Judge what was said, not delivery: ignore fillers, slips and transcription errors.
An answer to a different question, or no real answer, gets 0-2."""


def rounded(x):
    return int(x + 0.5)  # half up; round() rounds 6.5 to 6


def band(x):
    return next(i for i, (lo, hi) in enumerate(BANDS) if lo <= rounded(x) <= hi)


def grader_version():
    return hashlib.sha1((inspect.getsource(answer_evaluator) + settings.get("llm_model")).encode()).hexdigest()[:10]


# ---------- human grades ----------

def read_sheet():
    """The hand-grading sheet as rows of {id, score, question, transcript}; written blank on first use."""
    if not HUMAN.exists():
        write_sheet([{"id": c["id"], "score": "", "question": c["question"], "transcript": c["transcript"]} for c in CASES])
    with open(HUMAN, encoding="utf-8-sig", newline="") as f:  # -sig: Excel's "CSV UTF-8" adds a BOM
        return list(csv.DictReader(f))


def write_sheet(rows):
    with open(HUMAN, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "score", "question", "transcript"])
        w.writeheader()
        w.writerows(rows)


def human_scores():
    out = {}
    for r in read_sheet():
        s = (r.get("score") or "").strip()
        if s:
            try:
                v = float(s)
            except ValueError:
                v = -1
            if not 0 <= v <= 10:
                sys.exit(f"human_grades.csv, {r['id']}: score {s!r} is not a number from 0 to 10")
            out[r["id"]] = v
    return out


def by_hand():
    """Show each ungraded answer, without its label or the model's score, and save each score as it's typed."""
    rows = read_sheet()
    todo = [r for r in rows if not r["score"].strip()]
    print(f"{HOW_TO_GRADE}\n\n{len(todo)} of {len(rows)} left. Press Enter on an empty line to stop; you can resume later.")
    for n, r in enumerate(todo, 1):
        print(f"\n--- {r['id']} ({n}/{len(todo)}) ---\nQuestion: {r['question']}\n\nAnswer: \"{r['transcript']}\"\n")
        while True:
            s = input("Score 0-10: ").strip()
            if not s:
                return
            try:
                if 0 <= float(s) <= 10:
                    break
            except ValueError:
                pass
            print("A number from 0 to 10, please.")
        r["score"] = s
        write_sheet(rows)


# ---------- model grades ----------

def load_runs():
    return json.loads(MODEL.read_text(encoding="utf-8")) if MODEL.exists() else {}


def grade_with_model():
    """Grade every case this grader version hasn't scored yet (errors are retried on the next run)."""
    runs, version = load_runs(), grader_version()
    run = runs.setdefault(version, {"model": settings.get("llm_model"), "started": time.strftime("%Y-%m-%d %H:%M"), "grades": {}})
    todo = [c for c in CASES if (run["grades"].get(c["id"]) or {}).get("score") is None]
    print(f"grader {version} ({run['model']}): {len(todo)} of {len(CASES)} cases to grade")
    for n, c in enumerate(todo, 1):
        t = time.time()
        g = answer_evaluator.grade(c["question"], c["transcript"], c["domain"], c["difficulty"])
        run["grades"][c["id"]] = {"score": g.get("final_score"), "on_topic": g.get("on_topic"),
                                  "summary": str(g.get("candidate_summary", ""))[:240], "error": g.get("error"),
                                  "seconds": round(time.time() - t)}
        MODEL.write_text(json.dumps(runs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  {n}/{len(todo)} {c['id']} {c['kind']:9} score={g.get('final_score')} "
              f"on_topic={g.get('on_topic')} ({time.time() - t:.0f}s) {g.get('error') or ''}")
    return version


# ---------- report ----------

def report(version, human):
    run = load_runs().get(version)
    if not run:
        sys.exit(f"No model grades for grader {version} yet: run without --report first.")
    model = {k: g["score"] for k, g in run["grades"].items() if g.get("score") is not None}
    errors = [k for k, g in run["grades"].items() if g.get("score") is None]
    mean = lambda xs: f"{statistics.mean(xs):.1f}" if xs else "-"
    L = [f"# Grader agreement", "",
         f"Grader `{version}`: {run['model']}, run started {run['started']}. {len(CASES)} answers "
         f"({sum(c['source'] == 'saved' for c in CASES)} from saved sessions, the rest synthetic and labelled), "
         f"{len(model)} graded, {len(errors)} without a score{': ' + ', '.join(errors) if errors else ''}. "
         f"Human grades: {len(human)} of {len(CASES)}.", "",
         "## Mean score by kind of answer", "", "| Kind | Answers | Model | Human |", "|---|---|---|---|"]
    for kind in KINDS:
        ids = [c["id"] for c in CASES if c["kind"] == kind]
        L.append(f"| {kind} | {len(ids)} | {mean([model[i] for i in ids if i in model])} | {mean([human[i] for i in ids if i in human])} |")

    fails = [c for c in CASES if c["kind"] in ("off_topic", "empty") and model.get(c["id"], 0) > HIGH]
    L += ["", f"## Off-topic and empty answers scored above {HIGH}", ""]
    L += [f"- **{c['id']}** ({c['kind']}, {model[c['id']]}, on_topic={run['grades'][c['id']].get('on_topic')}): "
          f"{c['transcript'][:110]}... | question: {c['question'][:90]}..." for c in fails] or ["None."]

    pairs = [(c["id"], model[c["id"]], human[c["id"]]) for c in CASES if c["id"] in model and c["id"] in human]
    L += ["", "## Agreement with the human grades", ""]
    if not pairs:
        L.append("Waiting for human grades: fill in `human_grades.csv` (or run with `--by-hand`), then run with `--report`.")
    else:
        n = len(pairs)
        diffs = [m - h for _, m, h in pairs]
        exact = sum(rounded(m) == rounded(h) for _, m, h in pairs)
        near = sum(abs(rounded(m) - rounded(h)) <= 1 for _, m, h in pairs)
        L += [f"On {n} answers graded by both (model scores rounded to whole points):", "",
              f"- Exact: {exact}/{n} ({exact / n:.0%})",
              f"- Within ±1: {near}/{n} ({near / n:.0%})",
              f"- Mean absolute difference: {statistics.mean(abs(d) for d in diffs):.2f} points",
              f"- Mean of model minus human: {statistics.mean(diffs):+.2f} points (above 0: the model grades higher)", "",
              "Rows are the human's score, columns the model's:", "",
              "| human \\ model | " + " | ".join(f"{lo}-{hi}" for lo, hi in BANDS) + " |", "|---" * (len(BANDS) + 1) + "|"]
        for hb, (lo, hi) in enumerate(BANDS):
            cells = [sum(band(h) == hb and band(m) == mb for _, m, h in pairs) for mb in range(len(BANDS))]
            L.append(f"| **{lo}-{hi}** | " + " | ".join(str(x) if x else "." for x in cells) + " |")
        far = sorted((p for p in pairs if abs(p[1] - p[2]) >= 3), key=lambda p: -abs(p[1] - p[2]))
        kind = {c["id"]: c["kind"] for c in CASES}
        L += ["", "Off by 3 or more:", ""]
        L += [f"- {i} ({kind[i]}): model {m}, human {h:g}" for i, m, h in far] or ["None."]
    text = "\n".join(L) + "\n"
    RESULTS.write_text(text, encoding="utf-8")
    print("\n" + text)


if __name__ == "__main__":
    if "--by-hand" in sys.argv:
        by_hand()
    else:
        report(grader_version() if "--report" in sys.argv else grade_with_model(), human_scores())
