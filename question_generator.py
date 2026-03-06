import os
import json
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

class AssessmentQuestion(BaseModel):
    scenario: str = Field(description="A brief description of a realistic work scenario relevant to the job.")
    question: str = Field(description="A question that tests the candidate's judgment, decision-making, or problem-solving in this scenario.")
    evaluation_criteria: str = Field(description="Clearly defined criteria for what constitutes a good answer vs. a poor answer.")
    ideal_approach: str = Field(description="A brief summary of the ideal approach or solution to the scenario.")

class JD_Assessment(BaseModel):
    role: str
    company: str
    assessment_questions: list[AssessmentQuestion]

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: Please set the GEMINI_API_KEY environment variable.")
        return

    client = genai.Client()
    
    input_file = "final_parsed_jds.json"
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found. Run llm_parser.py first.")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        jds_dict = json.load(f)

    print(f"Loaded {len(jds_dict)} structured JDs. Generating tailored assessments...")

    final_assessments = {}
    
    for i, (filepath, jd_data) in enumerate(jds_dict.items()):
        # Skip entries with errors
        if "error" in jd_data:
            print(f"[{i+1}/{len(jds_dict)}] Skipping due to previous error: {filepath}")
            continue
            
        role = jd_data.get("role", "Unknown Role")
        # Extract company from filepath (e.g., "Deloitte\\...pdf" -> "Deloitte")
        company = filepath.split("\\")[0] if "\\" in filepath else "Unknown Company"
        
        print(f"[{i+1}/{len(jds_dict)}] Generating assessment for: {role} at {company}")
        
        prompt = f"""
        Create a tailored assessment for the following Job Description. 
        The assessment should contain 3 realistic, scenario-based questions that test the candidate's JUDGMENT, PRIORITIZATION, and PROBLEM-SOLVING skills rather than simple knowledge recall.
        
        Job Title: {role}
        Seniority: {jd_data.get('seniority')}
        Skills: {', '.join(jd_data.get('skills', []))}
        Domain: {jd_data.get('domain')}
        Key Responsibilities: {', '.join(jd_data.get('key_responsibilities', []))}
        
        Instructions:
        1. Each question must be based on a plausible 'Situation' or 'Scenario' the candidate might face in this specific role.
        2. The questions should force the candidate to make a trade-off or choose a strategy.
        3. Provide clear evaluation criteria for the interviewer.
        """

        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=JD_Assessment,
                    temperature=0.4, # Slightly higher for creativity in scenarios
                ),
            )
            
            assessment = json.loads(response.text)
            final_assessments[filepath] = assessment
            
        except Exception as e:
            print(f"Error generating assessment for {filepath}: {e}")
            final_assessments[filepath] = {"error": str(e)}

    # Save results
    output_file = "assessments.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_assessments, f, indent=2, ensure_ascii=False)
        
    print(f"\nSuccessfully generated {len(final_assessments)} assessments. Saved to {output_file}.")

if __name__ == "__main__":
    main()
