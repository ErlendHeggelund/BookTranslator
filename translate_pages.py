import os
import sys
import time
import argparse

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

def translate_text_with_backoff(text, target_lang='no', max_retries=5, initial_delay=2):
    if not GoogleTranslator:
        print("Error: deep-translator is not installed. Please install it using: pip install deep-translator")
        sys.exit(1)

    translator = GoogleTranslator(source='auto', target=target_lang)
    delay = initial_delay
    
    # If the text is empty or only whitespace, return it directly
    if not text.strip():
        return text

    # Split text into chunks if it is too long (Google Translate limit is 5000 characters)
    # Let's set a safe limit of 4000 characters.
    MAX_CHAR_LIMIT = 4000
    if len(text) > MAX_CHAR_LIMIT:
        print(f"Warning: Text length ({len(text)}) exceeds safe limit. Splitting into chunks.")
        # Split by paragraph first
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = []
        current_len = 0
        for p in paragraphs:
            if current_len + len(p) + 2 > MAX_CHAR_LIMIT:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = [p]
                    current_len = len(p)
                else:
                    # Single paragraph is too long! Split by lines
                    lines = p.split("\n")
                    for line in lines:
                        if len(line) > MAX_CHAR_LIMIT:
                            # Hard split
                            for i in range(0, len(line), MAX_CHAR_LIMIT):
                                chunks.append(line[i:i+MAX_CHAR_LIMIT])
                        else:
                            chunks.append(line)
            else:
                current_chunk.append(p)
                current_len += len(p) + 2
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
            
        translated_chunks = []
        for idx, chunk in enumerate(chunks):
            print(f"  Translating chunk {idx+1}/{len(chunks)}...")
            translated_chunk = translate_text_with_backoff(chunk, target_lang, max_retries, initial_delay)
            translated_chunks.append(translated_chunk)
        return "\n\n".join(translated_chunks)

    for attempt in range(max_retries):
        try:
            translated = translator.translate(text)
            return translated
        except Exception as e:
            print(f"Error translating text (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                raise e
            time.sleep(delay)
            delay *= 2

def translate_pages(src_dir, dest_dir, target_lang='no'):
    """
    Translates all page files in src_dir and writes them to dest_dir.
    """
    if not os.path.exists(src_dir):
        print(f"Error: Source directory '{src_dir}' does not exist.")
        sys.exit(1)

    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
        print(f"Created destination directory: {dest_dir}")
        
    # Get all .txt files and sort them numerically if possible
    files = [f for f in os.listdir(src_dir) if f.endswith(".txt")]
    
    def file_sort_key(filename):
        # Extract page number for proper sorting
        # e.g., page_10.txt -> 10
        name = os.path.splitext(filename)[0]
        parts = name.split("_")
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
        return filename
        
    files.sort(key=file_sort_key)
    
    total_files = len(files)
    print(f"Found {total_files} files to translate.")
    
    start_time = time.time()
    
    for idx, filename in enumerate(files):
        src_path = os.path.join(src_dir, filename)
        dest_path = os.path.join(dest_dir, filename)
        
        # Check if already translated
        if os.path.exists(dest_path):
            print(f"[{idx+1}/{total_files}] Skipping {filename} (already translated).")
            continue
            
        print(f"[{idx+1}/{total_files}] Translating {filename}...")
        
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            translated_content = translate_text_with_backoff(content, target_lang)
            
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(translated_content)
                
            # Add a small delay between requests to be gentle on the API
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Failed to translate {filename}: {e}")
            print("Stopping execution due to translation error.")
            sys.exit(1)
            
    elapsed = time.time() - start_time
    print(f"\nAll translations completed successfully in {elapsed:.2f} seconds!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Translate extracted page text files using deep-translator.")
    parser.add_argument("--src-dir", default="pages", help="Directory containing source text files (default: 'pages')")
    parser.add_argument("--dest-dir", default="pages_norwegian", help="Directory to save translated text files (default: 'pages_norwegian')")
    parser.add_argument("--target-lang", default="no", help="Target language code (default: 'no' / Norwegian)")
    
    args = parser.parse_args()
    
    translate_pages(args.src_dir, args.dest_dir, args.target_lang)
