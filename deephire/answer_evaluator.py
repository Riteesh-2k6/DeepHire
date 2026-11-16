import os
import json
import requests
import time
from typing import Dict, Any, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key from environment variables
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in environment variables")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

class AnswerEvaluator:
    def __init__(self, model="llama3-8b-8192"):
        self.model = model
        self.headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Evaluation rubric for technical interviews
        self.rubric = {
            "technical_accuracy": {
                "weight": 0.40,
                "description": "Correctness of technical concepts, implementation details, and factual information"
            },
            "problem_solving": {
                "weight": 0.30,
                "description": "Quality of approach to solving the problem, including algorithm choice, efficiency and complexity analysis"
            },
            "completeness": {
                "weight": 0.20,
                "description": "How thoroughly the answer addresses all aspects of the question including edge cases"
            },
            "optimization": {
                "weight": 0.10,
                "description": "Identification of optimizations, performance considerations, and technical trade-offs"
            }
        }

    def generate_ideal_answer(self, question: str, domain: str, difficulty: str) -> str:
        """Generate an ideal answer for comparison purposes"""
        system_prompt = f"""You are a senior technical interviewer for a {domain} position.
Generate a model answer for a {difficulty}-level technical interview question.
The answer should be comprehensive, technically accurate, and demonstrate best practices.
"""

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Question: {question}\n\nProvide an ideal answer:"}
            ],
            "temperature": 0.3,
            "max_tokens": 1500
        }
        
        try:
            response = requests.post(GROQ_API_URL, headers=self.headers, json=data)
            response.raise_for_status()
            result = response.json()
            
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"Error generating ideal answer: {str(e)}")
            return "Failed to generate ideal answer."

    def evaluate_answer(self, question: str, user_answer: str, domain: str, difficulty: str) -> Dict[str, Any]:
        """Evaluate a user's answer against an ideal answer"""
        # First generate an ideal answer
        ideal_answer = self.generate_ideal_answer(question, domain, difficulty)
        
        system_prompt = """You are an expert technical interviewer evaluating candidates' responses.
Evaluate the candidate's answer based on these criteria:

1. Technical Accuracy (40%): Correctness of technical concepts and implementation details
2. Problem Solving (30%): Quality of approach to solving the problem
3. Completeness (20%): How thoroughly the answer addresses all aspects of the question
4. Optimization (10%): Identification of optimizations and technical trade-offs

For each criterion, provide:
1. A score from 0-10
2. Brief justification for the score

Then calculate a final weighted score out of 10 based on the criteria weights.
Also provide 2-3 sentences of actionable feedback for improvement.

Format your response as JSON:
{
  "technical_accuracy": {"score": X, "justification": "..."},
  "problem_solving": {"score": X, "justification": "..."},
  "completeness": {"score": X, "justification": "..."},
  "optimization": {"score": X, "justification": "..."},
  "final_score": X,
  "feedback": "..."
}
"""

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"""
Question: {question}

Candidate's Answer:
{user_answer}

Ideal Answer (for reference):
{ideal_answer}

Evaluate the candidate's answer according to the criteria."""}
            ],
            "temperature": 0.2,
            "max_tokens": 1500,
            "response_format": {"type": "json_object"}
        }
        
        try:
            response = requests.post(GROQ_API_URL, headers=self.headers, json=data)
            response.raise_for_status()
            result = response.json()
            
            evaluation = json.loads(result["choices"][0]["message"]["content"])
            
            # Add the ideal answer to the evaluation
            evaluation["model_answer"] = ideal_answer
            
            return evaluation
        except Exception as e:
            print(f"Error evaluating answer: {str(e)}")
            return {
                "error": str(e),
                "final_score": 0,
                "feedback": "Failed to evaluate answer due to an error.",
                "model_answer": ideal_answer
            }

    def process_json_file(self, json_file_path: str) -> Dict[str, Any]:
        """Process a JSON file containing interview data and evaluate answers"""
        try:
            with open(json_file_path, 'r') as f:
                session_data = json.load(f)
                
            domain = session_data.get("domain", "fullstack")
            difficulty = session_data.get("difficulty", "medium")
            questions = session_data.get("questions", [])
            
            results = []
            total_score = 0
            
            for i, question_data in enumerate(questions):
                question_id = question_data.get("id")
                question_text = question_data.get("question_text")
                user_answer = question_data.get("user_answer", "")
                
                if not user_answer:
                    continue
                    
                print(f"Evaluating question {i+1}/{len(questions)}: {question_id}")
                
                # Evaluate answer
                evaluation = self.evaluate_answer(question_text, user_answer, domain, difficulty)
                
                # Save evaluation back to question data
                question_data["evaluation"] = evaluation
                
                # Add to results list
                results.append({
                    "question_id": question_id,
                    "question": question_text,
                    "user_answer": user_answer,
                    "model_answer": evaluation.get("model_answer", ""),
                    "evaluation_score": evaluation.get("final_score", 0),
                    "evaluation_feedback": evaluation.get("feedback", "")
                })
                
                total_score += evaluation.get("final_score", 0)
                
                # Small delay to avoid API rate limits
                time.sleep(0.5)
            
            # Calculate average score
            if results:
                avg_score = total_score / len(results)
            else:
                avg_score = 0
                
            # Update session data with evaluation results
            session_data["evaluated"] = True
            session_data["avg_score"] = avg_score
            session_data["evaluations"] = results
            
            # Save updated data back to file
            with open(json_file_path, 'w') as f:
                json.dump(session_data, f, indent=2)
                
            return {
                "session_id": session_data.get("session_id"),
                "session_info": {
                    "company": session_data.get("company", ""),
                    "domain": domain,
                    "difficulty": difficulty
                },
                "total_score": avg_score,
                "responses": results
            }
            
        except Exception as e:
            print(f"Error processing JSON file: {str(e)}")
            return {"error": str(e)}

# For command-line testing
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python answer_evaluator.py <session_json_file>")
        sys.exit(1)
        
    json_file = sys.argv[1]
    evaluator = AnswerEvaluator()
    results = evaluator.process_json_file(json_file)
    
    print(json.dumps(results, indent=2))