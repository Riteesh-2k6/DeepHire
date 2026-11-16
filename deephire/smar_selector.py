import sqlite3
import random
import json
company_dict = {
    "Google": 1,
    "Meta": 2,
    "Capgemini": 3,
    "Infosys": 4,
    "Apple": 5,
    "Netflix": 6,
    "Amazon": 7
}
domain_dict = {
    "Full Stack": 1,
    "Front End": 2,
    "Back End": 3,
    "Java": 4,
    "Python": 5,
    "AI/ML Dev": 6,
    "System Design": 7
}
difficulty_dict = {
    "Easy": 1,
    "Medium": 2,
    "Hard": 3
}
def smart_question_selector(input_json):
    session_id = input_json["session_id"]
    preferences = input_json["preferences"]
    company = company_dict[preferences["company"]]
    domain = domain_dict[preferences["domain"]]
    difficulty = difficulty_dict[preferences["difficulty"]]
    print(company,domain,difficulty)
    conn = sqlite3.connect('interview_questions.db')
    cursor = conn.cursor()

    # Step 1: Select x (1 ≤ x ≤ 6)
    x = random.randint(1, 6)

    # Step 2: Select x matching difficulty
    cursor.execute("""
        SELECT question_text FROM questions
        WHERE company_id = ? AND domain_id = ? AND difficulty_id = ?
        ORDER BY RANDOM() LIMIT ?
    """, (company, domain, difficulty, x))
    primary_questions = [row[0] for row in cursor.fetchall()]
    # Step 3: Select (10 - x) questions of other difficulties
    cursor.execute("""
        SELECT question_text FROM questions
        WHERE company_id = ? AND domain_id = ? AND difficulty_id != ?
        ORDER BY RANDOM() LIMIT ?
    """, (company, domain, difficulty, 10 - x))
    secondary_questions = [row[0] for row in cursor.fetchall()]
    conn.close()
    all_questions = primary_questions + secondary_questions
    random.shuffle(all_questions)

    # Create result dictionary
    result = {
        "session_id": session_id,
        "company":preferences["company"],
        "domain":preferences["domain"],
        "difficulty":preferences["difficulty"],
        "questions": [{"id": i+1, "question": q} for i, q in enumerate(all_questions)]
    }

    # Write result to sessions/{session_id}.json
    output_file = f"sessions/{session_id}.json"
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"Questions saved to {output_file}")

