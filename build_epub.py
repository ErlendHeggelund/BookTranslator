import os
import re
import sys
import hashlib
import argparse

try:
    from ebooklib import epub
except ImportError:
    epub = None

# Roman numeral parsing
def roman_to_int(s):
    roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    val = 0
    for i in range(len(s)):
        if i > 0 and roman_map[s[i]] > roman_map[s[i - 1]]:
            val += roman_map[s[i]] - 2 * roman_map[s[i - 1]]
        else:
            val += roman_map[s[i]]
    return val

def clean_footers(lines, title=None, author=None):
    while lines and not lines[-1].strip():
        lines.pop()
        
    footers_patterns = [
        r"^innhold\.$",
        r"^contents\.$",
        r"^indeks\.$",
        r"^index\.$"
    ]
    
    if title:
        escaped_title = re.escape(title.strip())
        footers_patterns.append(r"^" + escaped_title)
        # Also try first 3 words of title
        words = title.strip().split()
        if len(words) > 2:
            footers_patterns.append(r"^" + re.escape(" ".join(words[:3])))
            
    if author:
        escaped_author = re.escape(author.strip())
        footers_patterns.append(r"^" + escaped_author)

    # Legacy defaults for Devout Life
    footers_patterns.extend([
        r"^st\.\s+frans\s+av\s+salg",
        r"^st\.\s+francis\s+of\s+sales",
        r"^introduksjon\s+til\s+det\s+fromme\s+livet",
        r"^introduction\s+to\s+the\s+devout\s+life",
    ])
    
    footer_indices = []
    for idx in range(len(lines) - 1, max(-1, len(lines) - 6), -1):
        line = lines[idx].strip()
        if not line:
            continue
        is_footer = False
        for pattern in footers_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                is_footer = True
                break
        is_page_num = False
        if re.match(r'^\d+$', line) or re.match(r'^[ivxld]+$', line, re.IGNORECASE):
            is_page_num = True
            
        if is_footer or is_page_num:
            footer_indices.append(idx)
        else:
            if footer_indices:
                break
                
    for idx in sorted(footer_indices, reverse=True):
        lines.pop(idx)
        
    while lines and not lines[-1].strip():
        lines.pop()
        
    return lines

def extract_footnotes_for_page(lines, next_footnote_id):
    page_footnotes = []
    current_search_start = 0
    indices_to_remove = []
    
    while True:
        found_idx = -1
        for idx in range(current_search_start, len(lines)):
            if lines[idx].strip() == str(next_footnote_id):
                found_idx = idx
                break
                
        if found_idx == -1:
            break
            
        fn_text_lines = []
        j = found_idx + 1
        while j < len(lines):
            if re.match(r'^\d+$', lines[j].strip()):
                break
            fn_text_lines.append(lines[j])
            j += 1
            
        fn_text = " ".join([l.strip() for l in fn_text_lines if l.strip()])
        page_footnotes.append((next_footnote_id, fn_text))
        indices_to_remove.extend(range(found_idx, j))
        current_search_start = j
        next_footnote_id += 1
        
    remaining_lines = [lines[i] for i in range(len(lines)) if i not in indices_to_remove]
    return remaining_lines, page_footnotes, next_footnote_id

def assemble_paragraph(line_list):
    p_text = ""
    for i, line in enumerate(line_list):
        if i == 0:
            p_text = line
        else:
            if p_text.endswith("-"):
                if p_text[-2].isalpha() and line[0].isalpha():
                    p_text = p_text[:-1] + line
                else:
                    p_text = p_text + " " + line
            else:
                p_text = p_text + " " + line
    return p_text

def join_lines_to_paragraphs(lines):
    paragraphs = []
    current_para = []
    
    for line in lines:
        line_str = line.strip()
        if not line_str:
            if current_para:
                paragraphs.append(assemble_paragraph(current_para))
                current_para = []
        elif line_str.startswith("<h"):
            if current_para:
                paragraphs.append(assemble_paragraph(current_para))
                current_para = []
            paragraphs.append(line_str)
        else:
            current_para.append(line_str)
            
    if current_para:
        paragraphs.append(assemble_paragraph(current_para))
        
    return paragraphs

def build_epub(src_dir, output_path, title, author, lang='no', toc_start=2, toc_end=6, no_footnotes=False, no_toc=False, no_index=False):
    """
    Compiles page text files in src_dir into a single EPUB.
    """
    if not epub:
        print("Error: EbookLib (ebooklib) is not installed. Please install it using: pip install EbookLib")
        sys.exit(1)

    if not os.path.exists(src_dir):
        print(f"Error: Source directory '{src_dir}' does not exist.")
        sys.exit(1)

    files = [f for f in os.listdir(src_dir) if f.endswith(".txt")]
    def file_sort_key(filename):
        name = os.path.splitext(filename)[0]
        parts = name.split("_")
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
        return filename
    files.sort(key=file_sort_key)

    if not files:
        print(f"Error: No text files found in '{src_dir}'.")
        sys.exit(1)
        
    # Identify content range dynamically
    if no_toc or not toc_end:
        main_start = 1
    else:
        main_start = toc_end + 1
        
    if no_index:
        main_end = len(files)
    else:
        main_end = len(files) - 5 if len(files) > 10 else len(files)
        
    # Gather main files
    main_files = []
    for f in files:
        name = os.path.splitext(f)[0]
        parts = name.split("_")
        if len(parts) >= 2 and parts[1].isdigit():
            p_num = int(parts[1])
            if main_start <= p_num <= main_end:
                main_files.append(f)
                
    chapters = []
    current_chapter = None
    current_part = None
    next_footnote_id = 1
    
    print(f"Parsing {len(main_files)} main files for chapters...")
    for filename in main_files:
        src_path = os.path.join(src_dir, filename)
        with open(src_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        lines = content.split("\n")
        lines = clean_footers(lines, title, author)
        
        if not no_footnotes:
            lines, page_footnotes, next_footnote_id = extract_footnotes_for_page(lines, next_footnote_id)
        else:
            page_footnotes = []
            
        idx = 0
        while idx < len(lines):
            line = lines[idx].strip()
            if not line:
                idx += 1
                continue
                
            is_part = False
            if line.startswith("DEL ") or line.startswith("PART "):
                current_part = line
                is_part = True
                
            is_chap = False
            if line.startswith("KAPITTEL ") or line.startswith("CHAPTER "):
                is_chap = True
                
            # Generic checks for preface and index
            is_preface = ("forord" in line.lower() or "preface" in line.lower() or "prologue" in line.lower()) and len(line) < 30
            is_index = ("indeks" in line.lower() or "index" in line.lower()) and len(line) < 15
            
            if is_preface or is_chap or is_index:
                if current_chapter:
                    chapters.append(current_chapter)
                    
                headings = []
                if is_preface:
                    headings.append(line)
                    idx += 1
                elif is_index:
                    headings.append(line)
                    idx += 1
                elif is_chap:
                    if current_part:
                        headings.append(current_part)
                        current_part = None
                        
                    chap_title = line
                    idx += 1
                    # Heading continuation
                    while idx < len(lines):
                        next_line = lines[idx].strip()
                        if not next_line:
                            idx += 1
                            continue
                        if next_line.startswith("KAPITTEL") or next_line.startswith("CHAPTER") or next_line.startswith("DEL") or next_line.startswith("PART") or len(next_line) > 120 or next_line.endswith(".") or next_line[0].islower():
                            if len(next_line) < 80 and not chap_title.endswith("."):
                                chap_title += " " + next_line
                                idx += 1
                            break
                        chap_title += " " + next_line
                        idx += 1
                    headings.append(chap_title)
                    
                current_chapter = {
                    'headings': headings,
                    'body_lines': [],
                    'footnotes': [],
                    'filename': filename
                }
                continue
                
            if current_chapter:
                # Remove print page numbers in the text (single number or roman numeral on a line by itself)
                if re.match(r'^\d+$', line) or re.match(r'^[ivxld]+$', line, re.IGNORECASE):
                    idx += 1
                    continue
                if is_part:
                    current_chapter['body_lines'].append(f"<h3>{line}</h3>")
                else:
                    current_chapter['body_lines'].append(line)
                    
                for fid, fn_text in page_footnotes:
                    pattern = r'(?<!\d)' + str(fid) + r'(?!\d)'
                    if re.search(pattern, line):
                        if (fid, fn_text) not in current_chapter['footnotes']:
                            current_chapter['footnotes'].append((fid, fn_text))
                            
            else:
                # Handle text appearing before any chapter headings (e.g. initial preface pages)
                # Auto-create an initial chapter
                current_chapter = {
                    'headings': ["Innledning" if lang == 'no' else "Introduction"],
                    'body_lines': [line],
                    'footnotes': [],
                    'filename': filename
                }
                for fid, fn_text in page_footnotes:
                    pattern = r'(?<!\d)' + str(fid) + r'(?!\d)'
                    if re.search(pattern, line):
                        current_chapter['footnotes'].append((fid, fn_text))
                            
            idx += 1
            
    if current_chapter:
        chapters.append(current_chapter)
        
    print(f"Parsed {len(chapters)} chapters/sections.")
    
    # Parse Table of Contents from files if TOC range provided and not disabled
    toc_lines = []
    current_part_num = 1
    if not no_toc and toc_start and toc_end:
        print(f"Parsing TOC from pages {toc_start} to {toc_end}...")
        toc_files = [f"page_{i}.txt" for i in range(toc_start, toc_end + 1)]
        for filename in toc_files:
            src_path = os.path.join(src_dir, filename)
            if not os.path.exists(src_path):
                continue
            with open(src_path, "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n")
            lines = clean_footers(lines, title, author)
            
            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue
                    
                if re.match(r'^[ivxld]+$', line_str, re.IGNORECASE) or re.match(r'^\d+$', line_str):
                    continue
                    
                part_match = re.match(r'^(DEL|PART)\s+([IVXLCDM]+)\b', line_str, re.IGNORECASE)
                if part_match:
                    rom_num = part_match.group(2).upper()
                    current_part_num = roman_to_int(rom_num)
                    dest = f"part{current_part_num}_ch01.xhtml"
                    toc_lines.append(f'<li class="part-title"><a href="{dest}">{line_str}</a></li>')
                    continue
                    
                chap_match = re.match(r'^(KAPITTEL|CHAPTER)\s+([IVXLCDM]+)\b', line_str, re.IGNORECASE)
                if chap_match:
                    rom_num = chap_match.group(2).upper()
                    chap_num = roman_to_int(rom_num)
                    dest = f"part{current_part_num}_ch{chap_num:02d}.xhtml"
                    toc_lines.append(f'<li><a href="{dest}">{line_str}</a></li>')
                    continue
                    
                if "forord" in line_str.lower() or "preface" in line_str.lower() or "om denne boken" in line_str.lower():
                    toc_lines.append(f'<li><a href="preface.xhtml">{line_str}</a></li>')
                    continue
                    
                if "indeks" in line_str.lower() or "index" in line_str.lower() or "indekser" in line_str.lower():
                    toc_lines.append(f'<li><a href="index.xhtml">{line_str}</a></li>')
                    continue
                    
                if re.match(r'^[\s\.]+$', line_str) or re.match(r'^s\.\s+\w+$', line_str, re.IGNORECASE) or re.match(r'^s\.\s+\d+$', line_str, re.IGNORECASE):
                    continue
                    
                if toc_lines:
                    prev_item = toc_lines[-1]
                    match_a = re.match(r'^(<li><a href="[^"]+">)(.*?)(</a></li>)$', prev_item)
                    if match_a:
                        prefix, content_a, suffix = match_a.groups()
                        toc_lines[-1] = f"{prefix}{content_a} {line_str}{suffix}"
                        continue
                        
                toc_lines.append(f'<li>{line_str}</li>')
                
    # Parse Index pages if not disabled
    index_body_html = ""
    index_start = len(files) - 4
    if not no_index and index_start > main_start:
        print(f"Parsing Index from page {index_start} onwards...")
        index_lines = []
        index_files = [f"page_{i}.txt" for i in range(index_start, len(files) + 1)]
        for filename in index_files:
            src_path = os.path.join(src_dir, filename)
            if not os.path.exists(src_path):
                continue
            with open(src_path, "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n")
            lines = clean_footers(lines, title, author)
            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue
                if re.match(r'^\d+$', line_str) or re.match(r'^[ivxld]+$', line_str, re.IGNORECASE):
                    continue
                index_lines.append(line_str)
                
        # Assemble Index HTML
        index_paragraphs = []
        curr_para = []
        for line in index_lines:
            if line.isupper() and len(line) < 30:
                if curr_para:
                    index_paragraphs.append(" ".join(curr_para))
                    curr_para = []
                index_paragraphs.append(f"<h3>{line}</h3>")
            else:
                curr_para.append(line)
        if curr_para:
            index_paragraphs.append(" ".join(curr_para))
            
        for p in index_paragraphs:
            if p.startswith("<h3>"):
                index_body_html += p + "\n"
            else:
                index_body_html += f"<p>{p}</p>\n"
                
    # Build EPUB structure
    book = epub.EpubBook()
    
    # Generate unique book identifier
    hash_str = f"{title}-{author}"
    book_uuid = hashlib.md5(hash_str.encode('utf-8')).hexdigest()
    book.set_identifier(f'id_book_{book_uuid}')
    book.set_title(title)
    book.set_language(lang)
    book.add_author(author)
    
    # Title Page
    title_item = epub.EpubHtml(title='Tittelside' if lang == 'no' else 'Title Page', file_name='title.xhtml', lang=lang)
    title_item.content = f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{title}</title>
  <style>
    body {{ font-family: sans-serif; text-align: center; margin-top: 5em; }}
    h1 {{ font-size: 2.5em; margin-bottom: 0.5em; }}
    h2 {{ font-size: 1.8em; font-weight: normal; color: #555; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <h2>{author}</h2>
</body>
</html>"""
    book.add_item(title_item)
    
    # Table of Contents Page (if parsed)
    toc_item = None
    if toc_lines:
        toc_item = epub.EpubHtml(title='Innholdsfortegnelse' if lang == 'no' else 'Table of Contents', file_name='toc.xhtml', lang=lang)
        toc_item.content = f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>Innholdsfortegnelse</title>
  <style>
    body {{ font-family: sans-serif; margin: 2em; }}
    h1 {{ text-align: center; color: #333; }}
    ul {{ list-style-type: none; padding-left: 0; }}
    li {{ margin-bottom: 0.5em; line-height: 1.4; }}
    .part-title {{ font-weight: bold; margin-top: 1.5em; color: #111; font-size: 1.1em; }}
    a {{ text-decoration: none; color: #1a5f7a; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <h1>{"Innholdsfortegnelse" if lang == 'no' else "Table of Contents"}</h1>
  <ul>
    {"\n    ".join(toc_lines)}
  </ul>
</body>
</html>"""
        book.add_item(toc_item)
        
    chapter_items = []
    preface_item = None
    index_item = None
    
    # Map each parsed chapter to files
    part_counters = {}
    current_part_id = 1
    preface_count = 0
    index_count = 0
    
    for ch in chapters:
        title_text = ch['headings'][-1] if ch['headings'] else "Kapittel"
        if "forord" in title_text.lower() or "preface" in title_text.lower() or "innledning" in title_text.lower() or "introduction" in title_text.lower():
            preface_count += 1
            if preface_count == 1:
                ch['id'] = 'preface'
                ch['file_name'] = 'preface.xhtml'
            else:
                ch['id'] = f'preface{preface_count}'
                ch['file_name'] = f'preface{preface_count}.xhtml'
            ch['part_num'] = 0
        elif "indeks" in title_text.lower() or "index" in title_text.lower():
            index_count += 1
            if index_count == 1:
                ch['id'] = 'index'
                ch['file_name'] = 'index.xhtml'
            else:
                ch['id'] = f'index{index_count}'
                ch['file_name'] = f'index{index_count}.xhtml'
            ch['part_num'] = 99
        else:
            for h in ch['headings']:
                if h.startswith("DEL ") or h.startswith("PART "):
                    part_match = re.match(r'^(DEL|PART)\s+([IVXLCDM]+)\b', h, re.IGNORECASE)
                    if part_match:
                        current_part_id = roman_to_int(part_match.group(2).upper())
                        
            part_counters[current_part_id] = part_counters.get(current_part_id, 0) + 1
            ch['part_num'] = current_part_id
            ch['id'] = f"part{current_part_id}_ch{part_counters[current_part_id]:02d}"
            ch['file_name'] = f"{ch['id']}.xhtml"
            
    # Compile HTML and save chapters
    for ch in chapters:
        paragraphs = join_lines_to_paragraphs(ch['body_lines'])
        
        html_paras = []
        for p in paragraphs:
            if p.startswith("<h"):
                html_paras.append(p)
            else:
                p_html = p
                if not no_footnotes:
                    for fid, fn_text in ch['footnotes']:
                        pattern = r'(?<!\d)' + str(fid) + r'(?!\d)'
                        p_html = re.sub(pattern, f'<sup><a href="#fn{fid}" id="fnref{fid}" epub:type="noteref">{fid}</a></sup>', p_html)
                html_paras.append(f"<p>{p_html}</p>")
                
        heading_html = ""
        for h in ch['headings']:
            if h.startswith("DEL ") or h.startswith("PART "):
                heading_html += f"<h1>{h}</h1>\n"
            elif h.startswith("KAPITTEL ") or h.startswith("CHAPTER "):
                heading_html += f"<h2>{h}</h2>\n"
            else:
                heading_html += f"<h2>{h}</h2>\n"
                
        footnotes_html = ""
        if not no_footnotes and ch['footnotes']:
            footnotes_html += '<section class="footnotes" epub:type="footnotes">\n<hr/>\n'
            for fid, fn_text in ch['footnotes']:
                footnotes_html += f'<aside id="fn{fid}" epub:type="footnote">\n'
                footnotes_html += f'<p><sup>{fid}</sup> {fn_text} <a href="#fnref{fid}" epub:type="backlink">↩</a></p>\n'
                footnotes_html += '</aside>\n'
            footnotes_html += '</section>\n'
            
        title_text = ch['headings'][-1] if ch['headings'] else 'Kapittel'
        xhtml_content = f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <title>{title_text}</title>
  <style>
    body {{ font-family: sans-serif; line-height: 1.5; margin: 2em; }}
    h1 {{ text-align: center; margin-top: 2em; color: #333; }}
    h2 {{ text-align: center; margin-top: 1.5em; color: #444; }}
    h3 {{ text-align: center; color: #555; }}
    p {{ text-indent: 1em; margin: 0 0 0.5em 0; text-align: justify; }}
    .footnotes {{ margin-top: 2em; font-size: 0.95em; color: #555; }}
    aside {{ margin-bottom: 0.8em; }}
  </style>
</head>
<body>
{heading_html}
{"\n".join(html_paras)}
{footnotes_html}
</body>
</html>"""
        
        item = epub.EpubHtml(title=title_text, file_name=ch['file_name'], lang=lang)
        item.content = xhtml_content
        book.add_item(item)
        
        if ch['id'] == 'preface':
            preface_item = item
        elif ch['id'] == 'index':
            index_item = item
        else:
            chapter_items.append(item)
            
    # Add Index page if we generated one and it wasn't added
    if index_body_html and not index_item:
        index_xhtml = f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>Indeks</title>
  <style>
    body {{ font-family: sans-serif; line-height: 1.4; margin: 2em; }}
    h1 {{ text-align: center; color: #333; }}
    h3 {{ margin-top: 1.5em; color: #444; border-bottom: 1px solid #ccc; padding-bottom: 0.2em; }}
    p {{ margin: 0 0 0.5em 0; }}
  </style>
</head>
<body>
  <h1>{"Indeks" if lang == 'no' else "Index"}</h1>
  {index_body_html}
</body>
</html>"""
        index_item = epub.EpubHtml(title='Indeks' if lang == 'no' else 'Index', file_name='index.xhtml', lang=lang)
        index_item.content = index_xhtml
        book.add_item(index_item)
        
    # Spine definition
    book.spine = ['nav', title_item]
    if toc_item:
        book.spine.append(toc_item)
    if preface_item:
        book.spine.append(preface_item)
    book.spine.extend(chapter_items)
    if index_item:
        book.spine.append(index_item)
        
    # Metadata TOC links
    meta_toc = []
    if preface_item:
        meta_toc.append(epub.Link('preface.xhtml', 'Forord/Preface', 'preface'))
        
    part_chapters = {}
    for ch in chapters:
        if 'part_num' in ch and ch['part_num'] > 0 and ch['part_num'] < 90:
            part_chapters.setdefault(ch['part_num'], []).append(ch)
            
    for p_num in sorted(part_chapters.keys()):
        p_chaps = part_chapters[p_num]
        if not p_chaps:
            continue
        part_title = f"Del/Part {p_num}"
        for h in p_chaps[0]['headings']:
            if h.startswith("DEL ") or h.startswith("PART "):
                part_title = h
                break
        links = []
        for ch in p_chaps:
            chap_title = ch['headings'][-1] if ch['headings'] else "Kapittel"
            links.append(epub.Link(ch['file_name'], chap_title, ch['id']))
        meta_toc.append((epub.Section(part_title), tuple(links)))
        
    if index_item:
        meta_toc.append(epub.Link('index.xhtml', 'Indeks/Index', 'index'))
    book.toc = tuple(meta_toc)
    
    # Add navigation
    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())
    
    # Write EPUB
    epub.write_epub(output_path, book, {'epub3_pages': False})
    print(f"EPUB created successfully at: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile page text files into a single structured EPUB.")
    parser.add_argument("--src-dir", default="pages_norwegian", help="Folder containing text pages (default: 'pages_norwegian')")
    parser.add_argument("--output", default="book.epub", help="Path of the output EPUB file (default: 'book.epub')")
    parser.add_argument("--title", default="Oversatt bok", help="Title of the book")
    parser.add_argument("--author", default="Ukjent forfatter", help="Author of the book")
    parser.add_argument("--lang", default="no", help="Language code of the book (default: 'no')")
    parser.add_argument("--toc-start", type=int, default=2, help="Start page number of Table of Contents (default: 2)")
    parser.add_argument("--toc-end", type=int, default=6, help="End page number of Table of Contents (default: 6)")
    parser.add_argument("--no-footnotes", action="store_true", help="Disable footnote extraction")
    parser.add_argument("--no-toc", action="store_true", help="Disable Table of Contents parsing")
    parser.add_argument("--no-index", action="store_true", help="Disable Index page parsing at the end of the book")
    
    args = parser.parse_args()
    
    build_epub(
        src_dir=args.src_dir,
        output_path=args.output,
        title=args.title,
        author=args.author,
        lang=args.lang,
        toc_start=args.toc_start,
        toc_end=args.toc_end,
        no_footnotes=args.no_footnotes,
        no_toc=args.no_toc,
        no_index=args.no_index
    )

