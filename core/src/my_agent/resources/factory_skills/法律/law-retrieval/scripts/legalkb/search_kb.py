
import sys
import os
from pathlib import Path
from typing import Optional, List, Tuple
import argparse


def extract_text_from_pdf(path: Path, max_pages: Optional[int] = None) -> str:

    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = pdf.pages[:max_pages] if max_pages else pdf.pages
            return "\n".join(
                page.extract_text() or ""
                for page in pages
            )
    except ImportError:
        return f"[错误] 未安装 pdfplumber，请运行: pip install pdfplumber"
    except Exception as e:
        return f"[PDF 读取失败: {e}]"


def extract_text_from_docx(path: Path) -> str:

    try:
        from docx import Document
        doc = Document(path)
        return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
    except ImportError:
        return f"[错误] 未安装 python-docx，请运行: pip install python-docx"
    except Exception as e:
        return f"[DocX 读取失败: {e}]"


def search_file(path: Path, keyword: str, context_chars: int = 150) -> Optional[str]:

    suffix = path.suffix.lower()
    
    if suffix == ".pdf":
        text = extract_text_from_pdf(path)
    elif suffix in (".docx", ".doc"):
        text = extract_text_from_docx(path)
    else:
        return None
    
    if "错误" in text or "失败" in text:
        return text
    
    
    keyword_lower = keyword.lower()
    text_lower = text.lower()
    
    if keyword_lower not in text_lower:
        return None
    
    
    results = []
    start = 0
    while True:
        idx = text_lower.find(keyword_lower, start)
        if idx == -1:
            break
        s = max(0, idx - context_chars)
        e = min(len(text), idx + len(keyword) + context_chars)
        snippet = text[s:e].replace("\n", " ").strip()
        results.append(f"...{snippet}...")
        start = idx + len(keyword)
        if len(results) >= 3:  
            break
    
    return "\n".join(results)


def search_directory(directory: str, keywords: List[str], 
                      file_types: Optional[List[str]] = None,
                      max_files: int = 50) -> List[Tuple[str, str]]:











    if file_types is None:
        file_types = [".pdf", ".docx", ".doc"]
    
    dir_path = Path(directory)
    if not dir_path.exists():
        print(f"[ERROR] 目录不存在: {directory}", file=sys.stderr)
        return []
    
    matches = []
    file_count = 0
    
    for root, _, files in os.walk(dir_path):
        for fname in files:
            if file_count >= max_files:
                break
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in file_types:
                continue
            file_count += 1
            
            
            for kw in keywords:
                result = search_file(fpath, kw)
                if result:
                    matches.append((str(fpath), kw, result))
                    break  
    
    return matches


def print_results(matches: List[Tuple[str, str, str]], keywords: List[str]):

    if not matches:
        print(f"[未找到] 关键词 '{'/'.join(keywords)}' 在本地知识库中无匹配")
        return
    
    print(f"[找到 {len(matches)} 个相关文件]\n")
    for i, (fpath, kw, snippet) in enumerate(matches, 1):
        fname = Path(fpath).name
        print(f"--- {i}. {fname} (匹配词: {kw}) ---")
        print(snippet)
        print()


def main():
    parser = argparse.ArgumentParser(description="本地法律知识库全文搜索")
    parser.add_argument("directory", help="知识库根目录路径")
    parser.add_argument("keywords", nargs="+", help="搜索关键词（支持多个，OR逻辑）")
    parser.add_argument("--types", default=".pdf,.docx,.doc", 
                        help="限定文件类型，逗号分隔 (默认: .pdf,.docx,.doc)")
    parser.add_argument("--max-files", type=int, default=50,
                        help="最大扫描文件数 (默认: 50)")
    parser.add_argument("--context", type=int, default=150,
                        help="匹配片段前后字符数 (默认: 150)")
    
    args = parser.parse_args()
    types = [f".{t.strip('.')}" for t in args.types.split(",")]
    
    matches = search_directory(
        args.directory, 
        args.keywords,
        file_types=types,
        max_files=args.max_files
    )
    print_results(matches, args.keywords)


if __name__ == "__main__":
    main()
