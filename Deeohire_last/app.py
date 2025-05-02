from flask import Flask, render_template, request, jsonify, redirect, url_for
import uuid
import os
import json
from smar_selector import smart_question_selector
from answer_evaluator import AnswerEvaluator
import time
from werkzeug.utils import secure_filename
import requests
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
@app.route('/')
def index():
   return render_template('index.html')
# Blogs page route 
@app.route('/blog')
def blog():
    return render_template('blog.html')

@app.route('/blog1')
def blog1():
    return render_template('blogs/blog1.html')

@app.route('/blog2')
def blog2():
    return render_template('blogs/blog2.html')

@app.route('/blog3')
def blog3():
    return render_template('blogs/blog3.html')

@app.route('/blog4')
def blog4():
    return render_template('blogs/blog4.html')

@app.route('/blog5')
def blog5():
    return render_template('blogs/blog5.html')

@app.route('/blog6')
def blog6():
    return render_template('blogs/blog6.html')

@app.route('/blog7')
def blog7():
    return render_template('blogs/blog7.html')

@app.route('/blog8')
def blog8():
    return render_template('blogs/blog8.html')

@app.route('/blog9')
def blog9():
    return render_template('blogs/blog9.html')
@app.route('/interview', methods=['GET']) 
def interview():
    """Render the main selection page"""
    return render_template('interview.html')

@app.route('/submit-interview-preferences', methods=['POST'])
def submit_interview_preferences():
    # Get the JSON data from the request
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Extract the interview preferences
    company = data.get('company')
    domain = data.get('domain')
    difficulty = data.get('difficulty')
    
    # Validate the data
    if not all([company, domain, difficulty]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Generate a unique session ID for this interview session
    session_id = str(uuid.uuid4())
    
    # Create session data using smart_question_selector
    session_data = {
        'session_id': session_id,
        'preferences': {
            'company': company,
            'domain': domain,
            'difficulty': difficulty
        }
    }
    
    # Generate questions and store session data
    smart_question_selector(session_data)
    
    return jsonify(session_data)
@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    session_id = request.args.get('session')
    if not session_id:
        return redirect(url_for('index'))

    session_file = f"sessions/{session_id}.json"
    if not os.path.exists(session_file):
        return redirect(url_for('index'))

    with open(session_file, 'r') as f:
        session_data = json.load(f)

    if request.method == 'GET':
        return render_template('chatbot.html', session_data=session_data)

@app.route('/api/end-interview', methods=['POST'])
def end_interview():
    """API endpoint to end the interview early and move to evaluation"""
    data = request.json
    session_id = data.get('session_id')
    
    # Verify session exists
    if not os.path.exists(f"sessions/{session_id}.json"):
        return jsonify({"error": "Session not found"})
    
    # Load session data
    with open(f"sessions/{session_id}.json", 'r') as f:
        session_data = json.load(f)
    
    # Mark interview as complete
    session_data["is_complete"] = True
    
    # Save updated session data
    with open(f"sessions/{session_id}.json", 'w') as f:
        json.dump(session_data, f, indent=2)
    
    return jsonify({
        "success": True,
        "redirect": f"/evaluate?session={session_id}"
    })

@app.route('/evaluate', methods=['POST'])
def evaluate():
    try:
        session_json = request.get_json()

        if not session_json:
            return "Invalid or missing JSON data", 400

        # Save to a temporary file
        session_id = session_json.get("session_id", "latest")
        filename = f"{session_id}.json"
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(temp_path, 'w') as f:
            json.dump(session_json, f, indent=2)

# Now process this named file
        result_data = evaluator.process_json_file(temp_path)

        if "error" in result_data:
            return f"Evaluation error: {result_data['error']}", 500

        return render_template("results.html",
                               session_info=result_data["session_info"],
                               responses=result_data["responses"],
                               total_score=result_data["total_score"])
    except Exception as e:
        return f"Server error during evaluation: {str(e)}", 500
@app.route('/results')
def results():
    """Show the interview results"""
    session_id = request.args.get('session')
    
    # Verify session exists
    if not os.path.exists(f"sessions/{session_id}.json"):
        return redirect(url_for('index'))
    
    # Load session data
    with open(f"sessions/{session_id}.json", 'r') as f:
        session_data = json.load(f)
    
    # Check if evaluation is complete
    if not session_data.get("evaluated", False):
        # Process the evaluations if not already done
        evaluator.process_json_file(f"sessions/{session_id}.json")
        
        # Reload data after evaluation
        with open(f"sessions/{session_id}.json", 'r') as f:
            session_data = json.load(f)
    
    # Prepare data for the results template
    results_data = {
        "session_id": session_id,
        "session_info": {
            "company": session_data.get("company", ""),
            "domain": session_data.get("domain", ""),
            "difficulty": session_data.get("difficulty", "")
        },
        "total_score": session_data.get("avg_score", 0),
        "responses": [{
            "question": eval.get("question", ""),
            "answer": eval.get("answer", ""),
            "model_answer": eval.get("model_answer", ""),
            "score": eval.get("score", 0),
            "feedback": eval.get("feedback", "")
        } for eval in session_data.get("evaluations", [])]}
    
    return render_template('results.html', results_data)


if __name__ == '__main__':
    app.run(debug=True)