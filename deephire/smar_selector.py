import math
import os
import random
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "interview_questions.db")

company_dict = {"Google": 1, "Meta": 2, "Capgemini": 3, "Infosys": 4, "Apple": 5, "Netflix": 6, "Amazon": 7}
domain_dict = {"Full Stack": 1, "Front End": 2, "Back End": 3, "Java": 4, "Python": 5, "AI/ML Dev": 6, "System Design": 7}
difficulty_dict = {"Easy": 1, "Medium": 2, "Hard": 3}


def select_questions(company, domain, difficulty, count=10):
    """Up to 60% of the questions at the chosen difficulty (at least one), the rest from other levels, shuffled."""
    c, d, lvl = company_dict[company], domain_dict[domain], difficulty_dict[difficulty]
    primary = random.randint(1, max(1, math.ceil(count * 0.6)))
    with sqlite3.connect(DB_PATH) as conn:
        query = """SELECT question_text FROM questions
                   WHERE company_id = ? AND domain_id = ? AND difficulty_id {} ?
                   ORDER BY RANDOM() LIMIT ?"""
        picked = [r[0] for r in conn.execute(query.format("="), (c, d, lvl, primary))]
        picked += [r[0] for r in conn.execute(query.format("!="), (c, d, lvl, count - len(picked)))]
    random.shuffle(picked)
    return picked
