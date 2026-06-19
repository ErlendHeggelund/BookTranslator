import os
import sys
import argparse

# Set up path to allow importing from the current script's directory
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

try:
    import extract_text_from_pdf
except ImportError:
    extract_text_from_pdf = None

try:
    import translate_pages
except ImportError:
    translate_pages = None

try:
    import build_epub
except ImportError:
    build_epub = None

def main():
    parser = argparse.ArgumentParser(
        description="Orchestrator to extract text from a PDF, translate pages, and compile them into a structured EPUB."
    )
    # File & Folder Options
    parser.add_argument("--pdf", help="Path to PDF book to extract. Optional if page files already exist.")
    parser.add_argument("--src-dir", default="pages", help="Folder for source text pages (default: 'pages').")
    parser.add_argument("--trans-dir", default="pages_norwegian", help="Folder for translated text pages (default: 'pages_norwegian').")
    parser.add_argument("--output", default="Bok_Oversatt.epub", help="Path of the generated EPUB file (default: 'Bok_Oversatt.epub').")
    
    # Translation Options
    parser.add_argument("--target-lang", default="no", help="Target translation language code (default: 'no' / Norwegian).")
    
    # Metadata Options
    parser.add_argument("--title", default="Oversatt bok", help="Title of the output book (default: 'Oversatt bok').")
    parser.add_argument("--author", default="Ukjent forfatter", help="Author of the book (default: 'Ukjent forfatter').")
    
    # TOC & Layout Options
    parser.add_argument("--toc-start", type=int, default=2, help="Start page number of table of contents in PDF (default: 2).")
    parser.add_argument("--toc-end", type=int, default=6, help="End page number of table of contents in PDF (default: 6).")
    parser.add_argument("--no-footnotes", action="store_true", help="Disable footnote extraction and popup linking.")
    parser.add_argument("--no-toc", action="store_true", help="Disable parsing Table of Contents from pages.")
    parser.add_argument("--no-index", action="store_true", help="Disable parsing Index from final pages.")
    
    # Flow Control Options
    parser.add_argument("--skip-pdf", action="store_true", help="Skip PDF extraction step even if PDF path is provided.")
    parser.add_argument("--skip-translation", action="store_true", help="Skip translation step (uses existing files in trans-dir).")
    parser.add_argument("--skip-epub", action="store_true", help="Skip EPUB packaging step.")
    
    args = parser.parse_args()

    # Verify helper scripts are available
    missing_helpers = []
    if not extract_text_from_pdf:
        missing_helpers.append("extract_text_from_pdf.py")
    if not translate_pages:
        missing_helpers.append("translate_pages.py")
    if not build_epub:
        missing_helpers.append("build_epub.py")
        
    if missing_helpers:
        print(f"Error: The orchestrator requires the following helper scripts in the same folder: {', '.join(missing_helpers)}")
        print("Please ensure they are present in the same directory as book_translator.py.")
        sys.exit(1)

    print("======================================================================")
    print("                BOOK TRANSLATION PIPELINE ORCHESTRATOR                ")
    print("======================================================================")
    print(f"Title:        {args.title}")
    print(f"Author:       {args.author}")
    print(f"Target Lang:  {args.target_lang}")
    print(f"Source Dir:   {args.src-dir if hasattr(args, 'src-dir') else args.src_dir}")
    print(f"Trans Dir:    {args.trans-dir if hasattr(args, 'trans-dir') else args.trans_dir}")
    print(f"Output File:  {args.output}")
    print("======================================================================\n")

    # Step 1: Text extraction from PDF
    if args.pdf and not args.skip_pdf:
        print(f"--- STEP 1: Extracting text from PDF: {args.pdf} ---")
        extract_text_from_pdf.extract_pdf_to_txt(args.pdf, args.src_dir)
    else:
        print(f"--- STEP 1: Skipping PDF extraction (using existing files in '{args.src_dir}') ---")
        
    # Step 2: Translation
    if not args.skip_translation:
        print(f"\n--- STEP 2: Translating text pages in '{args.src_dir}' to '{args.trans_dir}' ---")
        translate_pages.translate_pages(args.src_dir, args.trans_dir, args.target_lang)
    else:
        print(f"\n--- STEP 2: Skipping translation (using existing files in '{args.trans_dir}') ---")
    
    # Step 3: EPUB Packaging
    if not args.skip_epub:
        print(f"\n--- STEP 3: Packaging translated pages into EPUB: {args.output} ---")
        build_epub.build_epub(
            src_dir=args.trans_dir,
            output_path=args.output,
            title=args.title,
            author=args.author,
            lang=args.target_lang,
            toc_start=args.toc_start,
            toc_end=args.toc_end,
            no_footnotes=args.no_footnotes,
            no_toc=args.no_toc,
            no_index=args.no_index
        )
    else:
        print(f"\n--- STEP 3: Skipping EPUB packaging ---")
        
    print("\n======================================================================")
    print("Pipeline run completed successfully!")
    print("======================================================================")

if __name__ == "__main__":
    main()
