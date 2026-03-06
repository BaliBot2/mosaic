from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional
from dotenv import load_dotenv
import os, json, re, fitz

load_dotenv()

app = Flask(__name__)
CORS(app)

# Setup Gemini Client
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# --- Pydantic Models ---
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

class JobDescription(BaseModel):
    role: str = Field(description="The formal job title or role.")
    seniority: str = Field(description="The seniority level.")
    skills: list[str] = Field(description="A list of skills.")
    domain: str = Field(description="The industry context.")
    key_responsibilities: list[str] = Field(description="Main duties.")

class AssessmentQuestion(BaseModel):
    scenario: str
    question: str
    evaluation_criteria: str
    ideal_approach: str

class JDAssessment(BaseModel):
    role: str
    company: str
    assessment_questions: list[AssessmentQuestion]

# --- Files & Folders ---
SUBMISSIONS_FILE = 'submissions.json'
SCORED_FILE = 'scored_candidates.json'
ASSESSMENTS_FILE = 'assessments.json'
UPLOAD_FOLDER = 'uploads'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def init_files():
    for f in [SUBMISSIONS_FILE, SCORED_FILE]:
        if not os.path.exists(f) or os.path.getsize(f) == 0:
            with open(f, 'w') as file:
                json.dump([], file)
    if not os.path.exists(ASSESSMENTS_FILE) or os.path.getsize(ASSESSMENTS_FILE) == 0:
        with open(ASSESSMENTS_FILE, 'w') as file:
            json.dump({}, file)

init_files()

# --- Processing Pipeline ---

def extract_text(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text("text", sort=True) + "\n\n"
    text = re.sub(r'\s{3,}', '  ', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()

def structure_jd(text):
    prompt = f"Extract structured data from this Job Description:\n\n{text}"
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=JobDescription,
            temperature=0.1
        )
    )
    return response.parsed

def generate_assessment(jd_data, company_name):
    prompt = f"""
    Create a tailored assessment for the following Job Description.
    Role: {jd_data.role}
    Company: {company_name}
    Skills: {', '.join(jd_data.skills)}
    Responsibilities: {', '.join(jd_data.key_responsibilities)}
    
    Instruction: Generate 3 scenario-based questions testing judgment and strategy.
    """
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=JDAssessment,
            temperature=0.4
        )
    )
    return response.parsed

def score_candidate(submission, assessments):
    jd_key = submission['jd_file']
    if jd_key not in assessments:
        raise ValueError(f"No assessment data for {jd_key}")
        
    jd_assessment = assessments[jd_key]
    candidate_responses = submission['responses']
    
    individual_scores = []
    for i, resp in enumerate(candidate_responses):
        q_data = jd_assessment['assessment_questions'][i]
        prompt = f"Evaluate response:\nScenario: {q_data['scenario']}\nQuestion: {q_data['question']}\nCandidate: {resp['response']}"
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"response_mime_type": "application/json", "response_schema": QuestionScore}
        )
        individual_scores.append(response.parsed)

    total_score = sum(s.score for s in individual_scores) // len(individual_scores)
    summary_prompt = f"Summarize evaluation for {submission['candidate_name']} ({submission['role']}). Scores: {json.dumps([s.model_dump() for s in individual_scores])}"
    
    summary_response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=summary_prompt,
        config={"response_mime_type": "application/json", "response_schema": CandidateEvaluation}
    )
    
    evaluation = summary_response.parsed
    evaluation.candidate_name = submission['candidate_name']
    evaluation.role = submission['role']
    evaluation.company = submission['company']
    evaluation.total_score = total_score
    return evaluation

# --- Routes ---

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

@app.route('/leaderboard')
def leaderboard():
    return send_from_directory('.', 'leaderboard.html')

@app.route('/leaderboard-data')
def leaderboard_data():
    if not os.path.exists(SCORED_FILE):
        return jsonify([])
    with open(SCORED_FILE, 'r') as f:
        data = json.load(f)
    return jsonify(data)

@app.route('/upload-jd', methods=['POST'])
def upload_jd():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
            
        filename = file.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # 1. Extract
        text = extract_text(filepath)
        
        # 2. Structure
        jd_data = structure_jd(text)
        
        # 3. Generate
        company_name = filename.split('_')[0] if '_' in filename else "Unknown"
        assessment = generate_assessment(jd_data, company_name)
        
        # Save to assessments.json
        with open(ASSESSMENTS_FILE, 'r') as f:
            assessments = json.load(f)
        
        jd_key = filename # Use filename as key
        assessments[jd_key] = assessment.model_dump()
        
        with open(ASSESSMENTS_FILE, 'w') as f:
            json.dump(assessments, f, indent=4)
            
        return jsonify({
            "status": "success",
            "jd_key": jd_key,
            "assessment": assessment.model_dump()
        }), 200
        
    except Exception as e:
        print(f"Error uploading JD: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/submit', methods=['POST'])
def submit():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data received"}), 400
        
        with open(SUBMISSIONS_FILE, 'r') as f:
            submissions = json.load(f)
        submissions.append(data)
        with open(SUBMISSIONS_FILE, 'w') as f:
            json.dump(submissions, f, indent=4)
            
        with open(ASSESSMENTS_FILE, 'r') as f:
            assessments = json.load(f)
            
        evaluation = score_candidate(data, assessments)
        
        with open(SCORED_FILE, 'r') as f:
            scored = json.load(f)
        scored.append(evaluation.model_dump())
        with open(SCORED_FILE, 'w') as f:
            json.dump(scored, f, indent=4)
            
        return jsonify({
            "status": "success", 
            "message": "Scored successfully",
            "evaluation": evaluation.model_dump()
        }), 200
    except Exception as e:
        print(f"Error processing submission: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Mosaic Backend Server running on http://localhost:8000")
    app.run(port=8000, debug=True)
