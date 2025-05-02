from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import json
import uuid
import requests
from answer_evaluator import AnswerEvaluator
evaluator = AnswerEvaluator()

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

session_data = {}  # Temp storage for evaluated sessions

@app.route('/')
def upload_page():
    return render_template('upload.html')

@app.route('/evaluate', methods=['POST'])
def evaluate():
    try:
        file = request.files.get('file')
        if not file or not file.filename.endswith('.json'):
            return jsonify(success=False, message="Invalid file type. Please upload a JSON file."), 400

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        print(f"[DEBUG] File saved at: {file_path}")

        with open(file_path, 'r') as f:
            interview_data = json.load(f)

        try:
            evaluator = AnswerEvaluator()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("[ERROR] Exception during evaluation:", str(e))  # Add this
            return jsonify(success=False, message=str(e)), 500
        try:
            result = evaluator.evaluate_interview(interview_data)
        except requests.exceptions.RequestException as re:
            return jsonify(success=False, message="Error communicating with the API. Please try again later."), 500

        session_id = result.get('session_id', str(uuid.uuid4()))
        session_data[session_id] = result

        result_path = os.path.join(UPLOAD_FOLDER, f"{session_id}.json")
        with open(result_path, 'w') as f:
            json.dump(result, f, indent=2)

        return jsonify(success=True, session_id=session_id)
    
    except json.JSONDecodeError:
        return jsonify(success=False, message="Invalid JSON format in uploaded file."), 400
    except Exception as e:
        import traceback
        traceback.print_exc()  # print full error to terminal
        return jsonify(success=False, message=str(e)), 500


@app.route('/results/<session_id>')
def show_results(session_id):
    if session_id not in session_data:
        result_path = os.path.join(UPLOAD_FOLDER, f"{session_id}.json")
        if os.path.exists(result_path):
            with open(result_path, 'r') as f:
                session_data[session_id] = json.load(f)
        else:
            return "Session not found", 404

    return render_template('results.html', evaluation=session_data[session_id])

@app.route('/download/<session_id>')
def download(session_id):
    file_path = os.path.join(UPLOAD_FOLDER, f"{session_id}.json")
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "File not found", 404

if __name__ == '__main__':
    app.run(debug=True, port=8000)
