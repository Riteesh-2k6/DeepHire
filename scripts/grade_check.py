"""Sanity check for the grading prompt against the real local model (not run by pytest: it's slow).

    python scripts/grade_check.py [rounds]

Off-topic answers must score low and a decent on-topic answer must score well. The off-topic
trie case is the one gpt-oss-20b once scored 9.0 by grading its own model answer.
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "deephire"))
import answer_evaluator  # noqa: E402

TRIE = ("Implement a basic trie data structure in Python to store a collection of strings. "
        "The trie should support insertion, search, and prefix matching.")
COSINE = ("Implement a Python function to compute the cosine similarity between two sparse vectors, "
          "each represented as a dictionary of feature names to weights.")
OFF_TOPIC = ("Um, so I would use a hash map to count each word. Uh, then I sort the counts and take the "
             "top five. That is order n log n, but a heap would make it n log k.")
ON_TOPIC_TRIE = ("So each node holds a dictionary from character to child node and a flag for end of word. "
                 "Insert walks the characters, creating children that don't exist, and sets the flag on the last node. "
                 "Search walks the same way and returns the flag; prefix matching returns true if the walk "
                 "finishes without falling off. Each operation is order of the word length. Uh, for memory you "
                 "could use a fixed array of 26 children if the alphabet is small.")

CASES = [("off-topic trie", TRIE, OFF_TOPIC, lambda s: s <= 3),
         ("off-topic cosine", COSINE, OFF_TOPIC, lambda s: s <= 3),
         ("on-topic trie", TRIE, ON_TOPIC_TRIE, lambda s: s >= 6)]


def check_follow_ups():
    """A real answer gets a short single follow-up inside the interview's deadline."""
    failures = 0
    for name, question, transcript in [("trie follow-up", TRIE, ON_TOPIC_TRIE), ("off-topic follow-up", TRIE, OFF_TOPIC)]:
        t = time.time()
        f = answer_evaluator.follow_up(question, transcript, "Python", "Medium")
        took = time.time() - t
        passed = bool(f) and f["question"].count("?") == 1 and len(f["question"].split()) <= 35 \
            and took < answer_evaluator.FOLLOW_UP_TIMEOUT_S
        failures += not passed
        print(f"{'PASS' if passed else 'FAIL'}  {name:18} ({took:.0f}s)  {f}")
    return failures


def main(rounds=1):
    failures = check_follow_ups()
    for _ in range(rounds):
        for name, question, transcript, ok in CASES:
            t = time.time()
            g = answer_evaluator.grade(question, transcript, "Python", "Medium")
            score = g.get("final_score")
            passed = score is not None and ok(score)
            failures += not passed
            print(f"{'PASS' if passed else 'FAIL'}  {name:18} score={score} on_topic={g.get('on_topic')} "
                  f"({time.time() - t:.0f}s)  {g.get('error') or g.get('candidate_summary', '')[:90]}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
