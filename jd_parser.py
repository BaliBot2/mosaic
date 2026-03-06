import os
import fitz
import re
import json

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts clean, sorted plain text content from a PDF file using PyMuPDF."""
    final_text = ""
    doc = None # Initialize doc to None
    try:
        doc = fitz.open(pdf_path)
        for page_num, page in enumerate(doc):
            try:
                page_text = page.get_text("text", sort=True).strip()
                if page_text:
                    # Basic cleaning
                    page_text = re.sub(r'\s{3,}', '  ', page_text) # Use double space
                    page_text = re.sub(r'\n\s*\n', '\n', page_text) # Single newline
                    final_text += page_text + "\n\n" # Separate pages
            except Exception as page_e:
                 print(f"PyMuPDF: Error processing page {page_num + 1} in '{os.path.basename(pdf_path)}': {page_e}")
        # Ensure doc is closed if it was opened
        if doc:
            doc.close()
        return final_text.strip()
    except FileNotFoundError:
        print(f"Error: PDF file not found at {pdf_path}")
        return ""
    except Exception as e:
        print(f"An unexpected error occurred processing PDF {pdf_path} with PyMuPDF: {e}")
        # Ensure doc is closed in case of error after opening
        if doc:
            try:
                doc.close()
            except:
                pass # Ignore errors during close on exception
        return ""

def main():
    data_dir = os.path.join("data", "pdfs")
    output_dict = {}
    
    if not os.path.exists(data_dir):
        print(f"Directory {data_dir} does not exist.")
        return

    print("Extracting text from all PDFs...")
    count = 0
    for root, _, files in os.walk(data_dir):
        for file in files:
            if file.lower().endswith(".pdf"):
                pdf_path = os.path.join(root, file)
                print(f"Processing: {pdf_path}")
                text = extract_text_from_pdf(pdf_path)
                
                # using relative path as key
                rel_path = os.path.relpath(pdf_path, data_dir)
                output_dict[rel_path] = text
                count += 1
                
    with open("extracted_pdf_texts.json", "w", encoding="utf-8") as f:
        json.dump(output_dict, f, indent=2, ensure_ascii=False)
        
    print(f"Successfully extracted text from {count} PDFs. Saved to extracted_pdf_texts.json.")

if __name__ == "__main__":
    main()
