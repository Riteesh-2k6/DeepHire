import os
import json
import requests
from typing import Dict, List, Any, Optional
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('GROQ_API_KEY')

class AnswerEvaluator:
    def __init__(self):
        self.api_keys = os.getenv('GROQ_API_KEYS', '').split(',')
        if not self.api_keys or not any(self.api_keys):
            raise ValueError("GROQ_API_KEYS is not set in the environment variables.")
        
        self.current_key_index = 0
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.headers = self._get_headers()
        self.model = "llama-3.3-70b-versatile"  # Default model

    def _get_headers(self) -> Dict[str, str]:
        """Get API headers with current API key."""
        return {
            "Authorization": f"Bearer {self.api_keys[self.current_key_index]}",
            "Content-Type": "application/json"
        }

    def _rotate_api_key(self) -> None:
        """Rotate to the next available API key."""
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self.headers = self._get_headers()

    def _call_groq_api(self, prompt: str, system_message: str) -> str:
        """Make a call to the Groq API with the given prompt and handle rate limits."""
        max_retries = len(self.api_keys)
        retries = 0

        while retries < max_retries:
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.5,
                    "max_tokens": 4096,
                    "top_p": 1,
                    "stream": False
                }

                response = requests.post(self.api_url, headers=self.headers, json=payload)
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]

            except requests.exceptions.RequestException as e:
                if hasattr(e, 'response') and e.response:
                    status_code = e.response.status_code
                    if status_code in [429, 500, 503]:  # Rate limit or server error
                        print(f"API call failed with status {status_code}, rotating API key...")
                        self._rotate_api_key()
                        retries += 1
                        if retries < max_retries:
                            time.sleep(1)  # Wait before retrying
                            continue
                print(f"API call failed: {e}")
                if hasattr(e, 'response') and e.response:
                    print(f"Response status code: {e.response.status_code}")
                    print(f"Response content: {e.response.content}")
                raise

    def _generate_summary(self, average_score: float, domain: str, difficulty: str, company: str, question_count: int) -> str:
        """Generate a summary of the interview evaluation."""
        # Define performance levels
        if average_score >= 8.5:
            performance = "excellent"
        elif average_score >= 7.0:
            performance = "good"
        elif average_score >= 5.0:
            performance = "fair"
        else:
            performance = "needs improvement"

        # Generate summary text
        summary = f"The candidate completed {question_count} {difficulty}-level questions in the {domain} domain for {company}. "
        summary += f"Overall performance was {performance} with an average score of {average_score}/10. "

        # Add recommendations based on performance
        if performance == "excellent":
            summary += "The candidate demonstrated exceptional technical knowledge and problem-solving abilities."
        elif performance == "good":
            summary += "The candidate showed solid understanding but has room for improvement in some areas."
        elif performance == "fair":
            summary += "The candidate needs to strengthen their technical skills and problem-solving approach."
        else:
            summary += "Significant improvement is needed across all evaluation criteria."

        return summary

    def _call_groq_api(self, prompt: str, system_message: str) -> str:
        """Make a call to the Groq API with the given prompt."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5,
            "max_tokens": 4096,
            "top_p": 1,
            "stream": False
        }
        
        try:
            response = requests.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            print(f"API call failed: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"Response status code: {e.response.status_code}")
                print(f"Response content: {e.response.content}")
            raise

    def generate_model_answer(self, question: str, domain: str, difficulty: str) -> str:
        """Generate a model answer for the given question."""
        system_message = """You are an expert in technical interviews, particularly for software engineering and related fields.
            You are tasked with generating a high-quality model answer to a technical interview question.
            Your answer should be comprehensive, technically accurate, and demonstrate best practices.
            Focus on clarity, depth of knowledge, and practical implementation details where appropriate."""
        
        prompt = f"""Generate a model answer for the following {difficulty} level technical interview question in the {domain} domain:

Question: {question}

Your model answer should showcase:
1. Clear understanding of the question
2. Technical accuracy and depth
3. Best practices and patterns
4. Consideration of edge cases
5. Trade-offs in the approach

Please provide a comprehensive and well-structured response that would be considered exemplary by interviewers at top tech companies."""

        return self._call_groq_api(prompt, system_message)

    def evaluate_answer(self, question: str, candidate_answer: str, model_answer: str, domain: str, difficulty: str) -> Dict[str, Any]:
        """Evaluate a candidate's answer against the model answer."""
        system_message = """You are an expert technical interview evaluator with experience in assessing candidates for top tech companies.
            Your task is to evaluate a candidate's answer against a model answer for a technical interview question.
            Provide a fair, objective, and detailed assessment focusing on technical accuracy, completeness, clarity, and overall quality."""
        
        prompt = f"""I need you to evaluate a candidate's response to a technical interview question. 

Question: {question}
Domain: {domain}
Difficulty: {difficulty}

Candidate's Answer:
---
{candidate_answer}
---

Model Answer:
---
{model_answer}
---

Please evaluate the candidate's answer based on the following criteria:
1. Correctness - Is the answer technically accurate and correct?
2. Completeness - Does it address all aspects of the question?
3. Clarity - Is the answer well-structured and clearly explained?
4. Technical Proficiency - Does it demonstrate appropriate technical knowledge?

For each criterion, assign a score from 1-10 (where 10 is perfect). 

Then, provide an overall score from 1-10 and a detailed feedback paragraph explaining the strengths and weaknesses of the answer.

Format your response as a JSON object with the following structure:
{{
  "correctness_score": number,
  "completeness_score": number,
  "clarity_score": number, 
  "technical_score": number,
  "overall_score": number,
  "feedback": "detailed feedback paragraph"
}}
"""

        try:
            result = self._call_groq_api(prompt, system_message)
            # Parse JSON from the response
            result_json = json.loads(result)
            return result_json
        except json.JSONDecodeError:
            # If JSON parsing fails, return a default structure with error message
            return {
                "correctness_score": 1,
                "completeness_score": 1,
                "clarity_score": 1,
                "technical_score": 1,
                "overall_score": 1,
                "feedback": "Unable to evaluate the answer. The response contained insufficient or invalid content."
            }

    def evaluate_interview(self, interview_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate all answers in an interview session."""
        session_id = interview_data.get("session_id", "unknown")
        company = interview_data.get("company", "unknown")
        domain = interview_data.get("domain", "unknown")
        difficulty = interview_data.get("difficulty", "unknown")
        answers = interview_data.get("answers", [])
        
        print(f"Starting evaluation for session {session_id}...")
        
        evaluated_questions = []
        total_score = 0
        valid_question_count = 0
        scores = {
            "correctness": 0,
            "completeness": 0,
            "clarity": 0,
            "technical": 0
        }
        
        for item in answers:
            question = item.get("question")
            answer = item.get("answer")
            
            # Skip items with missing questions
            if not question:
                continue
                
            valid_question_count += 1
            print(f"Evaluating question {valid_question_count}...")
            
            # Generate model answer
            try:
                model_answer = self.generate_model_answer(question, domain, difficulty)
                time.sleep(1)  # Small delay to avoid rate limiting
            except Exception as e:
                print(f"Error generating model answer: {e}")
                model_answer = "Unable to generate model answer due to an error."
            
            # Evaluate the answer
            try:
                evaluation = self.evaluate_answer(question, answer, model_answer, domain, difficulty)
                time.sleep(1)  # Small delay to avoid rate limiting
            except Exception as e:
                print(f"Error evaluating answer: {e}")
                evaluation = {
                    "correctness_score": 0,
                    "completeness_score": 0,
                    "clarity_score": 0,
                    "technical_score": 0,
                    "overall_score": 0,
                    "feedback": f"Evaluation failed due to an error: {str(e)}"
                }
            
            question_score = evaluation.get("overall_score", 0)
            total_score += question_score
            
            # Update category scores
            scores["correctness"] += evaluation.get("correctness_score", 0)
            scores["completeness"] += evaluation.get("completeness_score", 0)
            scores["clarity"] += evaluation.get("clarity_score", 0)
            scores["technical"] += evaluation.get("technical_score", 0)
            
            evaluated_questions.append({
                "question": question,
                "answer": answer,
                "model_answer": model_answer,
                "score": question_score,
                "feedback": evaluation.get("feedback", "")
            })
        
        # Calculate average scores
        if valid_question_count > 0:
            average_score = round(total_score / valid_question_count, 1)
            correctness_score = round(scores["correctness"] / valid_question_count, 1)
            completeness_score = round(scores["completeness"] / valid_question_count, 1)
            clarity_score = round(scores["clarity"] / valid_question_count, 1)
            technical_score = round(scores["technical"] / valid_question_count, 1)
        else:
            average_score = 0
            correctness_score = 0
            completeness_score = 0
            clarity_score = 0
            technical_score = 0
        
        # Generate overall summary
        summary = self._generate_summary(average_score, domain, difficulty, company, valid_question_count)
        
        return {
            "session_id": session_id,
            "company": company,
            "domain": domain,
            "difficulty": difficulty,
            "evaluated_at": datetime.now().isoformat(),
            "average_score": average_score,
            "correctness_score": correctness_score,
            "completeness_score": completeness_score,
            "clarity_score": clarity_score,
            "technical_score": technical_score,
            "summary": summary,
            "questions": evaluated_questions
        }