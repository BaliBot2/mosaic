import json
import os
from google import genai
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv

load_dotenv()

# Setup Gemini Client
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

class QuestionScore(BaseModel):
    score: int
    reasoning: str

class CandidateEvaluation(BaseModel):
    candidate_name: str
    role: str
    company: str
    total_score: int
    strengths: List[str]
    areas_for_improvement: List[str]
    recommendation: str # Advance, Hold, Reject
    detailed_feedback: str

def score_submissions():
    if not os.path.exists('submissions.json'):
        print("No submissions found.")
        return

    with open('submissions.json', 'r') as f:
        submissions = json.load(f)

    if not os.path.exists('assessments.json'):
        print("No assessments found.")
        return

    with open('assessments.json', 'r') as f:
        assessments = json.load(f)

    results = []

    for sub in submissions:
        print(f"Scoring submission for: {sub['candidate_name']}...")
        
        jd_key = sub['jd_file']
        if jd_key not in assessments:
            print(f"Warning: No assessment data for {jd_key}")
            continue
            
        jd_assessment = assessments[jd_key]
        candidate_responses = sub['responses']
        
        individual_scores = []
        
        for i, resp in enumerate(candidate_responses):
            # Find the corresponding question in assessments
            q_data = jd_assessment['assessment_questions'][i]
            
            prompt = f"""
            Evaluate a candidate's response to an assessment question.
            
            Scenario: {q_data['scenario']}
            Question: {q_data['question']}
            Evaluation Criteria: {q_data['evaluation_criteria']}
            Ideal Approach: {q_data['ideal_approach']}
            
            Candidate's Response: "{resp['response']}"
            
            Provide a score from 0 to 100 and a brief reasoning for the score.
            """
            
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": QuestionScore
                }
            )
            
            score_data = response.parsed
            individual_scores.append(score_data)

        # Calculate final evaluation
        total_score = sum(s.score for s in individual_scores) // len(individual_scores)
        
        summary_prompt = f"""
        Summarize the performance of candidate {sub['candidate_name']} for the role of {sub['role']}.
        
        Scores and Reasoning: {json.dumps([s.model_dump() for s in individual_scores])}
        
        Generate a final evaluation including:
        1. Strengths
        2. Areas for improvement
        3. Recommendation (Advance, Hold, Reject)
        4. A detailed feedback paragraph.
        """
        
        summary_response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=summary_prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": CandidateEvaluation
            }
        )
        
        final_eval = summary_response.parsed
        # Inject metadata
        final_eval.candidate_name = sub['candidate_name']
        final_eval.role = sub['role']
        final_eval.company = sub['company']
        final_eval.total_score = total_score
        
        results.append(final_eval.model_dump())

    # Save results
    with open('scored_candidates.json', 'w') as f:
        json.dump(results, f, indent=4)
        
    print(f"Scored {len(results)} candidates. Results saved to scored_candidates.json")

if __name__ == "__main__":
    score_submissions()
