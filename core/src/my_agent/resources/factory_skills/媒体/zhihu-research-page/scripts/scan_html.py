# -*- coding: utf-8 -*-

















import re, os, sys, glob, argparse
from collections import defaultdict



if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BLOCK_TAGS = {'p', 'table', 'div', 'h2', 'h3', 'h4', 'h5', 'h6',
              'blockquote', 'ul', 'ol', 'li', 'section', 'article'}


def check_code_balance(html, filepath):
    opens = len(re.findall(r'<\s*code[^>]*>', html, re.I))
    closes = len(re.findall(r'</\s*code\s*>', html, re.I))
    if opens != closes:
        return [(filepath, 'A.code_balance',
                 f'<code> 开启 {opens} 个，闭合 {closes} 个，差额 {opens - closes} '
                 f'（正数=缺闭合，负数=多余闭合）')]
    return []


def check_block_in_code(html, filepath):
    issues = []
    
    pattern = re.compile(r'<\s*code[^>]*>(.*?)</\s*code\s*>', re.S | re.I)
    for match in pattern.finditer(html):
        inner = match.group(1)
        for tag in BLOCK_TAGS:
            if re.search(rf'<\s*{tag}[\s>]', inner, re.I):
                ctx = inner[:120].replace('\n', ' ').strip()
                issues.append((filepath, 'B.block_in_code',
                               f'<code> 内包含块级标签 <{tag}>，'
                               f'导致 font-family: monospace 泄漏到正文。上下文: {ctx}'))
                break  
    return issues


def check_suspicious_close(html, filepath):
    issues = []
    
    suspicious = re.findall(r'</\s*([^>]*[\u4e00-\u9fff][^>]*)>', html)
    seen = set()
    for s in suspicious:
        if s not in seen:
            seen.add(s)
            issues.append((filepath, 'C.suspicious_close',
                           f'疑似异常闭合标签: </{s}> '
                           f'（可能意欲写作 </code> 或 </strong> 但被中文字符污染）'))
    return issues


def check_code_strong_cross(html, filepath):
    issues = []
    
    if re.search(r'<\s*code[^>]*>\s*<\s*strong[^>]*>.*?</\s*code\s*>.*?</\s*strong\s*>', html, re.S | re.I):
        issues.append((filepath, 'D.cross_nest',
                       '检测到 <code> 与 <strong> 交叉嵌套，可能导致字体异常'))
    return issues


def scan(drafts, verbose=True):
    all_issues = []
    stats = {'scanned': 0, 'clean': 0}
    for fp in drafts:
        if not os.path.exists(fp):
            continue
        stats['scanned'] += 1
        html = open(fp, encoding='utf-8', errors='ignore').read()
        issues = (
            check_code_balance(html, fp) +
            check_block_in_code(html, fp) +
            check_suspicious_close(html, fp) +
            check_code_strong_cross(html, fp)
        )
        all_issues.extend(issues)
        if not issues:
            stats['clean'] += 1

    if verbose:
        if not all_issues:
            print(f"✅ 扫描 {stats['scanned']} 个文件，全部通过")
        else:
            
            by_cat = defaultdict(list)
            for _, cat, detail in all_issues:
                by_cat[cat].append(detail)
            print(f"⚠️ 扫描 {stats['scanned']} 个文件，发现 {len(all_issues)} 个问题 "
                  f"({stats['scanned'] - stats['clean']} 个文件):\n")
            for cat, details in sorted(by_cat.items()):
                print(f"  [{cat}] ({len(details)} 处)")
                for d in details:
                    print(f"    → {d}")
                print()

    return all_issues, stats


def main():
    parser = argparse.ArgumentParser(description='HTML 章节草稿 <code> 标签预扫描')
    parser.add_argument('--fix', action='store_true', help='交互式修复 (TODO)')
    parser.add_argument('--files', nargs='*', help='指定文件，默认扫描所有 _draft_*.html')
    args = parser.parse_args()

    drafts = args.files if args.files else (
        glob.glob('./other/_draft_*.html') + glob.glob('./other/_draft_ch_*.html') +
        glob.glob('_draft_*.html') + glob.glob('_draft_ch_*.html')  
    )
    drafts = sorted(set(drafts))

    if not drafts:
        print("[提示] 未找到 _draft_*.html 文件，跳过扫描")
        return 0

    if args.fix:
        print("[TODO] 自动修复模式尚未实现，请手工修复上述问题后重新运行")
        return 1

    issues, _ = scan(drafts, verbose=True)

    if issues:
        print("💡 建议：修复以上问题后运行 python ./other/assemble.py")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
