from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional
from dotenv import load_dotenv
import os, json, re, fitz

print("Working dir:", os.getcwd())
print("Files:", os.listdir())

load_dotenv()

app = Flask(__name__)
CORS(app)

# Setup Gemini Client
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("WARNING: GEMINI_API_KEY environment variable is missing or empty!")
else:
    # Print partially masked key for confirmation
    masked_key = api_key[:4] + "***" + api_key[-4:] if len(api_key) > 8 else "***"
    print(f"INFO: Successfully loaded GEMINI_API_KEY ({masked_key})")

client = genai.Client(api_key=api_key)

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
    assessment_questions: list[dict] = Field(description="A list of objects, each containing a 'scenario', 'question', 'evaluation_criteria', and 'ideal_approach'.")

# --- Files & Folders ---
SUBMISSIONS_FILE = 'submissions.json'
SCORED_FILE = 'scored_candidates.json'
ASSESSMENTS_FILE = 'assessments.json'
UPLOAD_FOLDER = 'uploads'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def init_files():
    print("INFO: Initializing files...")
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
    print(f"INFO: Extracting text from {pdf_path}")
    try:
        print(f"DEBUG: Does file exist? {os.path.exists(pdf_path)}")
        if os.path.exists(pdf_path):
            print(f"DEBUG: File size: {os.path.getsize(pdf_path)} bytes")
            
        doc = fitz.open(pdf_path)
        print(f"DEBUG: PDF opened successfully. Number of pages: {len(doc)}")
        
        text = ""
        for i, page in enumerate(doc):
            page_text = page.get_text("text", sort=True)
            print(f"DEBUG: Extracted {len(page_text)} chars from page {i+1}")
            text += page_text + "\n\n"
            
        text = re.sub(r'\s{3,}', '  ', text)
        text = re.sub(r'\n\s*\n', '\n', text)
        print(f"DEBUG: Total extracted text length: {len(text)}")
        return text.strip()
    except Exception as e:
        print(f"ERROR: Failed to extract text from '{pdf_path}'")
        print(f"ERROR DETAILS: {str(e)}")
        import traceback
        traceback.print_exc()
        raise e

def structure_jd(text):
    print("INFO: Structuring JD text...")
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
    print(f"INFO: Generating assessment for company {company_name}")
    prompt = f"""
    Create a tailored assessment for the following Job Description.
    Role: {jd_data.role}
    Company: {company_name}
    Skills: {', '.join(jd_data.skills)}
    Responsibilities: {', '.join(jd_data.key_responsibilities)}
    
    Instruction: Generate 3 scenario-based questions testing judgment and strategy.
    
    You must return a valid JSON object with the following exact structure and keys:
    {{
        "role": "string",
        "company": "string",
        "assessment_questions": [
            {{
                "scenario": "string",
                "question": "string",
                "evaluation_criteria": "string",
                "ideal_approach": "string"
            }}
        ]
    }}
    """
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.4
        )
    )
    
    # Parse the returned JSON text string into a Python dict safely
    text = response.text
    if text.startswith("```json"):
        text = text[7:-3]
    elif text.startswith("```"):
        text = text[3:-3]
        
    parsed_json = json.loads(text.strip())
    # Return as a JDAssessment model so the rest of the app doesn't break
    return JDAssessment(**parsed_json)

def score_candidate(submission, assessments):
    print(f"INFO: Scoring candidate {submission.get('candidate_name', 'Unknown')}")
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

@app.route('/admin')
def admin_dashboard():
    return send_from_directory('.', 'admin.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/assessments.json')
def get_assessments():
    return send_from_directory('.', ASSESSMENTS_FILE)

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
        print("INFO: Received request to upload JD...")
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
            
        filename = file.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # 1. Extract
        print(f"INFO: Step 1 - Extracting text from {filepath}")
        text = extract_text(filepath)
        
        # 2. Structure
        print("INFO: Step 2 - Structuring JD...")
        jd_data = structure_jd(text)
        
        # 3. Generate
        print("INFO: Step 3 - Generating assessment based on JD...")
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
        print("INFO: Received candidate submission...")
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
