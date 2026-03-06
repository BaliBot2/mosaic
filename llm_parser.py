import os
import json
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

class JobDescription(BaseModel):
    role: str = Field(description="The formal job title or role.")
    seniority: str = Field(description="The seniority level, such as Junior, Mid-Level, Senior, Lead, Executive, etc.")
    skills: list[str] = Field(description="A list of required or preferred skills (technical and soft).")
    domain: str = Field(description="The industry or domain context (e.g., Finance, Tech, Healthcare, Consulting).")
    key_responsibilities: list[str] = Field(description="A list of the main duties and responsibilities.")

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: Please set the GEMINI_API_KEY environment variable.")
        return

    client = genai.Client()
    
    input_file = "extracted_pdf_texts.json"
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found. Run jd_parser.py first.")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        texts_dict = json.load(f)

    print(f"Loaded {len(texts_dict)} extracted texts. Starting LLM structuring...")

    final_results = {}
    
    # Process each PDF text
    for i, (filepath, text) in enumerate(texts_dict.items()):
        print(f"[{i+1}/{len(texts_dict)}] Analyzing: {filepath}")
        
        prompt = f"""
        Extract the role, seniority, skills, domain, and key responsibilities from the following Job Description text.
        If any field is missing or ambiguous, infer the best answer from the context or leave it blank if completely unknown.
        
        Job Description Text:
        {text}
        """

        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=JobDescription,
                    temperature=0.1,
                ),
            )
            
            # response.text is guaranteed to be JSON matching the schema
            parsed_json = json.loads(response.text)
            final_results[filepath] = parsed_json
            
        except Exception as e:
            print(f"Error analyzing {filepath}: {e}")
            final_results[filepath] = {"error": str(e)}

    # Save final results
    output_file = "final_parsed_jds.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_results, f, indent=2, ensure_ascii=False)
        
    print(f"\nSuccessfully parsed Job Descriptions. Saved to {output_file}.")

if __name__ == "__main__":
    main()
