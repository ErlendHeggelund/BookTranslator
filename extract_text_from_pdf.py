import os
import sys
import argparse

try:
    import fitz  # PyMuPDF is imported as fitz
except ImportError:
    fitz = None

def extract_pdf_to_txt(pdf_path, output_folder):
    """
    Extracts text from a PDF and saves each page as a separate .txt file.
    """
    if not fitz:
        print("Error: PyMuPDF (fitz) is not installed. Please install it using: pip install pymupdf")
        sys.exit(1)

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"Error opening PDF '{pdf_path}': {e}")
        sys.exit(1)

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        
        output_filename = f"page_{page_num + 1}.txt"
        output_filepath = os.path.join(output_folder, output_filename)
        
        with open(output_filepath, "w", encoding="utf-8") as text_file:
            text_file.write(text)
            
        print(f"Saved: {output_filepath}")

    doc.close()
    print("\nExtraction complete!")

if __name__ == "__main__":
    # Set up the argument parser
    parser = argparse.ArgumentParser(description="Extract text from a PDF into one text file per page.")
    
    # Add a required argument for the PDF path
    parser.add_argument("pdf_path", help="The path to the PDF file you want to extract.")
    
    # Add an optional argument for the output directory
    parser.add_argument("-o", "--output", default="extracted_pages", 
                        help="The folder where text files will be saved (default: 'extracted_pages').")
    
    # Parse the arguments provided by the user
    args = parser.parse_args()
    
    # Verify the PDF file actually exists before trying to extract it
    if not os.path.exists(args.pdf_path):
        print(f"Error: The file '{args.pdf_path}' was not found.")
        sys.exit(1)
    else:
        extract_pdf_to_txt(args.pdf_path, args.output)