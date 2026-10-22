#!/usr/bin/env python3
# -*- coding: utf-8 -*-









import argparse
import hashlib
import json
import os
import re
import sys
import time


DEFAULT_EXCLUDE_DIRS = {
    
    'vendor', 'node_modules', 'dist', 'build', '__pycache__', '.cache',
    
    '.git', '.hg', '.svn',
    
    '.ai-memory',
    
    '.codebuddy',   
    '.vscode',      
    '.idea',        
    '.claude',      
    '.cursor',      
    '.zed',         
    '.fleet',       
    '.sublime',     
    
    '.trae',        
    '.qoder',       
    
    '.windsurf',    
    '.codeium',     
    '.atom',        
    '.brackets',    
    '.vs',          
    '.metadata',    
    '.settings',    
    '.gradle',      
    'nbproject',    
    'target',       
}


_EXCLUDE_DIRS = set(DEFAULT_EXCLUDE_DIRS)


def load_exclude_dirs(root, extra=None):




    dirs = set(DEFAULT_EXCLUDE_DIRS)
    gi = os.path.join(root, '.graphignore')
    if os.path.isfile(gi):
        try:
            with open(gi, encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        dirs.add(line.rstrip('/\\'))
        except Exception:
            pass
    if extra:
        dirs.update(x.strip().rstrip('/\\') for x in extra.split(',') if x.strip())
    return dirs


SRC_EXTS = ('.php', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx',
            '.py', '.java', '.htm', '.html', '.css', '.scss', '.less')


RE_REQ_STMT = re.compile(r"(?:require|include)(?:_once)?\s*\(?\s*(.+?)\s*\)?\s*;", re.I | re.S)
RE_STR = re.compile(r"['\"]([^'\"]+)['\"]")
RE_DYNAMIC_MARK = re.compile(r"\$\w+")  
RE_CLASS = [
    re.compile(r"(?:class|interface|trait|enum)\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w\s,]+))?"),
    re.compile(r"(?:public\s+|private\s+|protected\s+)?function\s+(\w+)\s*\("),
]

RE_NAMESPACE = re.compile(r"^\s*namespace\s+([\w\\]+)\s*;", re.M)
RE_USE = re.compile(r"^\s*use\s+([\w\\]+)(?:\s+as\s+(\w+))?\s*;", re.M)
RE_NEW_FQN = re.compile(r"new\s+\\?([\w\\]+)\s*\(")            

RE_PY_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\s+\w+|import\s+([\w.]+))", re.M)
RE_JS_REQUIRE = re.compile(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
RE_JS_IMPORT = re.compile(r"import\s+(?:[^'\"(]*?\s+from\s+)?['\"]([^'\"]+)['\"]")
RE_JS_DYNAMIC_IMPORT = re.compile(r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
RE_JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", re.M)
RE_JAVA_PKG = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)

RE_TP_IMPORT = re.compile(r"(import|vendor|Loader::import)\s*\(\s*['\"]([^'\"]+)['\"]")


RE_TPL_INCLUDE = re.compile(
    r"\{\s*[a-z]*:?include\b[^}]*?\bfile\s*=\s*['\"]([^'\"]+)['\"]", re.I)
RE_TPL_REQUIRE = re.compile(r"template\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")  

RE_CSS_IMPORT = re.compile(r"@import\s+(?:url\()?\s*['\"]?([^'\"()\s;]+)['\"]?\s*\)?\s*;", re.I)
RE_HTML_LINK = re.compile(r"<link\b[^>]*\bhref\s*=\s*['\"]([^'\"]+)['\"]", re.I)
RE_HTML_SCRIPT = re.compile(r"<script\b[^>]*\bsrc\s*=\s*['\"]([^'\"]+)['\"]", re.I)




def _resolve_const_include(head, lit, rel, const_table, root):





    lit = lit or ''
    base = ''
    ok = True
    if re.match(r"^[A-Z_][A-Z0-9_]*$", head):
        base = resolve_const(head, const_table, root) if head in const_table else None
        if base is None:
            ok = False
    else:  
        for tok in re.split(r"\s*\.\s*", head):
            rb = resolve_const(tok, const_table, root) if tok in const_table else None
            if rb is None:
                ok = False
                break
            base = (base.rstrip('/') + '/' + rb.lstrip('/')) if base else rb
    if not ok:
        return None
    base = os.path.normpath(base) if base else ''
    if lit:
        lit2 = lit.lstrip('/')
        if base and (base.startswith('/') or re.match(r'^[A-Za-z]:', base) or os.path.isabs(base)):
            target = os.path.normpath(base.rstrip('/') + '/' + lit2)
        else:
            target = os.path.normpath(os.path.join(base, lit2)) if base else os.path.normpath(lit2)
    else:
        target = base
    if base and not (target.startswith('/') or re.match(r'^[A-Za-z]:', target) or os.path.isabs(target)):
        target = os.path.normpath(os.path.join(root, target))
    return target


def read_text(path):




    with open(path, 'rb') as f:
        raw = f.read()
    if raw.startswith(b'\xef\xbb\xbf'):
        raw = raw[3:]
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return raw.decode('gbk')
        except UnicodeDecodeError:
            return raw.decode('utf-8', errors='ignore')


def strip_php_comments(text):








    
    out_chars = []
    in_str = False
    quote = ''
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_str:
            if ch == '\\' and i + 1 < n:
                out_chars.append(text[i:i + 2])
                i += 2
                continue
            out_chars.append(ch)
            if ch == quote:
                in_str = False
            i += 1
        else:
            if ch in ('"', "'"):
                in_str = True
                quote = ch
                out_chars.append(ch)
                i += 1
            elif ch == '/' and i + 1 < n and text[i + 1] == '*':
                end = text.find('*/', i + 2)
                if end == -1:
                    nl = text.find('\n', i)
                    if nl == -1:
                        nl = n
                    out_chars.append('\n' * text[i:nl].count('\n'))
                    i = nl
                else:
                    out_chars.append('\n' * text[i:end + 2].count('\n'))
                    i = end + 2
            else:
                out_chars.append(ch)
                i += 1
    text = ''.join(out_chars)
    
    out = []
    in_heredoc = False
    heredoc_tag = ''
    for line in text.split('\n'):
        if in_heredoc:
            out.append(line)
            if line.strip().rstrip(';,').rstrip() == heredoc_tag:
                in_heredoc = False
            continue
        m = re.match(r'^\s*<<<?\s*([\'"]?)(\w+)\1', line)
        if m:
            in_heredoc = True
            heredoc_tag = m.group(2)
            out.append(line)
            continue
        
        in_s = False
        quote = ''
        i = 0
        n = len(line)
        cut = -1
        while i < n:
            ch = line[i]
            if in_s:
                if ch == '\\':
                    i += 2
                    continue
                if ch == quote:
                    in_s = False
            else:
                if ch in ('"', "'"):
                    in_s = True
                    quote = ch
                elif ch == '#':
                    cut = i
                    break
                elif ch == '/' and i + 1 < n and line[i + 1] == '/':
                    cut = i
                    break
            i += 1
        if cut >= 0:
            
            head = line[:cut].rstrip()
            if head == '' or head.endswith((';', '}', '{', ')', '?')):
                out.append(line[:cut])
                continue
        out.append(line)
    return '\n'.join(out)


def extract_includes(text, rel, root, const_table=None):






    text = strip_php_comments(text)
    const_table = const_table or {}
    includes = []
    for m in RE_REQ_STMT.finditer(text):
        expr = m.group(1).strip()
        
        if '__DIR__' in expr or 'dirname(' in expr:
            sm = RE_STR.search(expr)
            if sm:
                raw = sm.group(1)
                target = os.path.normpath(os.path.join(os.path.dirname(rel), raw.lstrip('/')))
                includes.append(target)
            continue
        
        
        cm = re.match(
            r"^((?:[A-Z_][A-Z0-9_]*)(?:\s*\.\s*[A-Z_][A-Z0-9_]*)*)"
            r"\s*\.\s*['\"]([^'\"]*)['\"]$", expr) or \
            re.match(r"^([A-Z_][A-Z0-9_]*)$", expr)
        if cm:
            target = _resolve_const_include(cm.group(1),
                                            cm.group(2) if len(cm.groups()) >= 2 else '',
                                            rel, const_table, root)
            if target is not None:
                includes.append(target)
                continue
            
        
        sm = RE_STR.search(expr)
        if not sm:
            continue
        raw = sm.group(1)
        
        if RE_DYNAMIC_MARK.search(expr):
            continue
        if raw.startswith('/') or re.match(r'^[A-Za-z]:', raw):
            target = os.path.normpath(raw)
        elif raw.startswith('./') or raw.startswith('../'):
            target = os.path.normpath(os.path.join(os.path.dirname(rel), raw))
        else:
            
            target = os.path.normpath(os.path.join(os.path.dirname(rel), raw))
            if not os.path.exists(target):
                target = os.path.normpath(os.path.join(root, raw))
        includes.append(target)
    return includes


def file_hash(path):

    try:
        h = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _safe_mtime(path):

    try:
        return os.path.getmtime(path)
    except Exception:
        return None


def detect_lsp(root):

    import shutil
    avail = {}
    
    try:
        avail['php'] = bool(shutil.which('intelephense') or shutil.which('phpactor'))
    except Exception:
        avail['php'] = False
    
    for lang in ('js', 'python', 'java', 'go'):
        avail[lang] = False
    return avail



RE_DEFINE = re.compile(
    r"define\s*\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*,\s*(.+?)\s*\)\s*;",
    re.I | re.S)
RE_CONST_DECL = re.compile(
    r"(?:public\s+|private\s+|protected\s+|final\s+|static\s+)*"
    r"const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+?)\s*;", re.I)


def extract_defines(text, rel):

    out = {}
    for m in RE_DEFINE.finditer(text):
        out[m.group(1)] = (m.group(2).strip(), rel)
    for m in RE_CONST_DECL.finditer(text):
        out[m.group(1)] = (m.group(2).strip(), rel)
    return out


def _resolve_segment(seg, const_table, root, seen):

    seg = seg.strip()
    if not seg:
        return ''
    sm = re.match(r"^['\"]([^'\"]*)['\"]$", seg)
    if sm:
        return sm.group(1)
    dm = re.match(r"^dirname\(\s*(.*?)\s*\)$", seg)
    if dm:
        inner = _resolve_segment(dm.group(1), const_table, root, seen)
        if inner is None:
            return None
        return os.path.dirname(inner)
    if re.match(r"^[A-Z_][A-Z0-9_]*$", seg):
        return resolve_const(seg, const_table, root, seen)
    return None  


def _resolve_const_rhs(raw, defining_rel, const_table, root, seen):

    raw = raw.strip()
    sm = re.match(r"^['\"]([^'\"]*)['\"]$", raw)
    if sm:
        return sm.group(1)
    work = raw
    if '__DIR__' in work:
        work = work.replace('__DIR__',
                            "'" + os.path.normpath(os.path.join(root,
                                os.path.dirname(defining_rel))).replace(os.sep, '/') + "'")
    if '__FILE__' in work:
        work = work.replace('__FILE__',
                            "'" + os.path.normpath(os.path.join(root,
                                defining_rel)).replace(os.sep, '/') + "'")
    
    parts = re.split(r"\s+\.\s+", work)
    res = ''
    for p in parts:
        if p.strip() == '':
            continue
        seg = _resolve_segment(p, const_table, root, seen)
        if seg is None:
            return None
        res += seg
    if res:
        res = os.path.normpath(res)
        
        if os.path.isabs(res) and res.startswith(os.path.abspath(root)):
            res = os.path.relpath(res, os.path.abspath(root)).replace(os.sep, '/')
            if res == '.':
                res = ''  
        return res
    return None


def resolve_const(name, const_table, root, seen=None):

    if seen is None:
        seen = set()
    if name in seen:
        return None
    entry = const_table.get(name)
    if not entry:
        return None
    raw, drel = entry
    seen.add(name)
    return _resolve_const_rhs(raw, drel, const_table, root, seen)


def parse_composer(root):





    out = {'psr4': {}, 'psr0': {}, 'files': [], 'classmap': []}
    cj = os.path.join(root, 'composer.json')
    if not os.path.isfile(cj):
        return out
    try:
        data = json.load(open(cj, encoding='utf-8', errors='ignore'))
    except Exception:
        return out
    al = data.get('autoload', {})
    for kind, key in (('psr4', 'psr-4'), ('psr0', 'psr-0')):
        for pref, d in (al.get(key) or {}).items():
            pref = pref.rstrip('/').rstrip('\\')  
            if isinstance(d, list):
                for x in d:
                    out[kind][pref] = x.rstrip('/').rstrip('\\')
            else:
                out[kind][pref] = d.rstrip('/').rstrip('\\')
    for f in (al.get('files') or []):
        out['files'].append(f)
    for cm in (al.get('classmap') or []):
        out['classmap'].append(cm)
    return out


def fqn_to_file(fqn, composer, root):

    fqn = fqn.lstrip('\\')
    parts = fqn.split('\\')
    
    for pref in sorted(composer['psr4'], key=len, reverse=True):
        if fqn == pref or fqn.startswith(pref + '\\'):
            rest = fqn[len(pref):].lstrip('\\').split('\\')
            d = composer['psr4'][pref]
            rel = os.path.normpath(os.path.join(d, *rest)) + '.php'
            if os.path.isfile(os.path.join(root, rel)):
                return rel.replace(os.sep, '/')
            return rel.replace(os.sep, '/')  
    
    for pref in sorted(composer['psr0'], key=len, reverse=True):
        if fqn == pref or fqn.startswith(pref + '\\'):
            rest = fqn[len(pref):].lstrip('\\').replace('\\', '/').replace('_', '/')
            rest_parts = [p for p in rest.split('/') if p]
            d = composer['psr0'][pref]
            rel = os.path.normpath(os.path.join(d, *rest_parts)) + '.php'
            if os.path.isfile(os.path.join(root, rel)):
                return rel.replace(os.sep, '/')
            return rel.replace(os.sep, '/')
    return None


def resolve_module(spec, lang, rel, root):



    spec = spec.strip()
    if not spec:
        return None
    
    rel_native = rel.replace('/', os.sep)
    src_dir = os.path.dirname(rel_native)
    src_full = os.path.join(root, src_dir) if src_dir else root
    if lang == 'py':
        parts = spec.split('.')
        if parts and parts[0] == '':
            parts = parts[1:]  
        cands = []
        for base in (src_full, root):
            cands.append(os.path.join(base, *parts) + '.py')
            cands.append(os.path.join(base, *parts, '__init__.py'))
        for c in cands:
            if os.path.isfile(c):
                return os.path.relpath(c, root).replace(os.sep, '/')
        return None
    if lang in ('js', 'ts'):
        if spec.startswith('./') or spec.startswith('../'):
            base = os.path.normpath(os.path.join(src_full, spec))
            
            if os.path.splitext(spec)[1]:
                if os.path.isfile(base):
                    return os.path.relpath(base, root).replace(os.sep, '/')
            for ext in ('.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs', '.json', '.css', '.scss', '.less'):
                c = base + ext
                if os.path.isfile(c):
                    return os.path.relpath(c, root).replace(os.sep, '/')
            for idx in ('index.js', 'index.ts', 'index.jsx', 'index.tsx'):
                c = os.path.join(base, idx)
                if os.path.isfile(c):
                    return os.path.relpath(c, root).replace(os.sep, '/')
            return None
        
        nm_dirs = [os.path.join(root, 'node_modules')]
        if src_dir:
            nm_dirs.append(os.path.join(root, src_dir, 'node_modules'))
        for nm in (spec, spec.lstrip('@')):
            for top in nm_dirs:
                c = os.path.join(top, nm)
                for entry in ('index.js', 'index.ts', 'index.jsx', 'index.tsx', 'src/index.js', 'src/index.ts'):
                    if os.path.isfile(os.path.join(c, entry)):
                        return os.path.relpath(os.path.join(c, entry), root).replace(os.sep, '/')
        return None
    if lang == 'java':
        parts = spec.split('.')
        rest = parts[:-1] if spec.endswith('.*') else parts
        relp = os.path.normpath(os.path.join(*rest)) + '.java'
        c = os.path.join(root, relp)
        if os.path.isfile(c):
            return os.path.relpath(c, root).replace(os.sep, '/')
        
        for dp, _, fns in os.walk(root):
            if any(x in dp for x in _EXCLUDE_DIRS):
                continue
            cand = os.path.join(dp, relp)
            if os.path.isfile(cand):
                return os.path.relpath(cand, root).replace(os.sep, '/')
        return None
    return None


def resolve_tp_import(spec, root, const_table):











    spec = spec.strip()
    if not spec or '.' not in spec:
        return None  
    parts = spec.split('.')
    head = parts[0]
    if spec.startswith('@'):
        base = resolve_const('APP_PATH', const_table, root) or 'application'
        parts = parts[1:]                      
        suffix = '.class.php'
    elif head == 'Think':
        tp = resolve_const('THINK_PATH', const_table, root) or \
            resolve_const('LIB_PATH', const_table, root) or 'ThinkPHP'
        base = (tp.rstrip('/') + '/Lib') if tp else 'ThinkPHP/Lib'
        parts = parts[1:]                      
        suffix = '.class.php'
    elif head in ('ORG', 'Com'):
        ep = resolve_const('EXTEND_PATH', const_table, root) or 'Extend/Library'
        base = (ep.rstrip('/') + '/Library') if ep else 'Extend/Library'
        
        suffix = '.class.php'
    elif head == 'Vendor':
        vp = resolve_const('VENDOR_PATH', const_table, root) or 'Vendor'
        base = vp.rstrip('/') if vp else 'Vendor'
        parts = parts[1:]                      
        suffix = '.class.php'
    else:  
        base = resolve_const('APP_PATH', const_table, root) or 'application'
        suffix = '.class.php'
    if not base or not parts:
        return None
    relp = os.path.normpath(os.path.join(base, *parts)) + suffix
    c = os.path.join(root, relp)
    if os.path.isfile(c):
        return os.path.relpath(c, root).replace(os.sep, '/')
    
    if suffix == '.class.php':
        c2 = os.path.join(root, os.path.normpath(os.path.join(base, *parts)) + '.php')
        if os.path.isfile(c2):
            return os.path.relpath(c2, root).replace(os.sep, '/')
    return None


def extract_file(path, root, const_table=None):

    text = ''
    try:
        text = read_text(path)
    except Exception:
        return {'includes': [], 'classes': [], 'calls': [], 'namespace': None,
                'uses': [], 'tpl_includes': []}
    rel = os.path.relpath(path, root).replace(os.sep, '/')
    
    PHP_EXTS = ('.php', '.inc', '.phtml', '.php3', '.php4', '.php5')
    
    
    code = strip_php_comments(text) if rel.endswith(PHP_EXTS) else text
    includes = extract_includes(text, rel, root, const_table) if rel.endswith(PHP_EXTS) else []
    
    
    if rel.endswith(PHP_EXTS):
        ns_m = RE_NAMESPACE.search(code)
        namespace = ns_m.group(1) if ns_m else None
        uses = [{'fqn': m.group(1), 'alias': m.group(2)} for m in RE_USE.finditer(code)]
        classes = []
        for m in RE_CLASS[0].finditer(code):
            cls = m.group(1)
            ext = m.group(2)
            impl = m.group(3)
            classes.append({'name': cls, 'line': code[:m.start()].count('\n') + 1,
                            'extends': ext, 'implements': impl})
        funcs = []
        for m in RE_CLASS[1].finditer(code):
            funcs.append(m.group(1))
        
        
        
        calls = []
        for m in re.finditer(r"new\s+(\w+)\s*\(", code):
            calls.append(m.group(1))
        for m in re.finditer(r"(\w+)::\w+", code):
            calls.append(m.group(1))
        
        new_fqns = [m.group(1) for m in RE_NEW_FQN.finditer(code)]
        
        tp_imports = [(m.group(1), m.group(2)) for m in RE_TP_IMPORT.finditer(code)]
    else:
        namespace = None
        uses = []
        classes = []
        funcs = []
        calls = []
        new_fqns = []
        tp_imports = []
    
    tpl_includes = []
    for m in RE_TPL_INCLUDE.finditer(text):
        tpl_includes.append(m.group(1))
    for m in RE_TPL_REQUIRE.finditer(text):
        tpl_includes.append(m.group(1))
    
    lang = None
    if rel.endswith('.py'):
        lang = 'py'
    elif rel.endswith(('.js', '.jsx', '.mjs', '.cjs')):
        lang = 'js'
    elif rel.endswith(('.ts', '.tsx')):
        lang = 'ts'
    elif rel.endswith('.java'):
        lang = 'java'
    module_imports = []
    if lang == 'py':
        for m in RE_PY_IMPORT.finditer(text):
            module_imports.append(m.group(1) or m.group(2))
    elif lang in ('js', 'ts'):
        for m in RE_JS_REQUIRE.finditer(text):
            module_imports.append(m.group(1))
        for m in RE_JS_IMPORT.finditer(text):
            module_imports.append(m.group(1))
        for m in RE_JS_DYNAMIC_IMPORT.finditer(text):
            module_imports.append(m.group(1))
    elif lang == 'java':
        java_pkg = RE_JAVA_PKG.search(text)
        for m in RE_JAVA_IMPORT.finditer(text):
            module_imports.append(m.group(1))
    
    css_imports = []
    if rel.endswith(('.css', '.scss', '.less')):
        for m in RE_CSS_IMPORT.finditer(text):
            css_imports.append(m.group(1))
    
    
    html_assets = []
    if rel.endswith(('.php', '.htm', '.html')):
        for m in RE_HTML_LINK.finditer(text):
            if m.group(1).endswith(('.css', '.scss', '.less', '.js', '.jsx',
                                     '.ts', '.tsx', '.mjs', '.cjs')):
                html_assets.append(m.group(1))
        for m in RE_HTML_SCRIPT.finditer(text):
            if m.group(1).endswith(('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs')):
                html_assets.append(m.group(1))
    return {'rel': rel, 'includes': includes, 'classes': classes,
            'funcs': funcs, 'calls': calls, 'namespace': namespace,
            'uses': uses, 'tpl_includes': tpl_includes, 'new_fqns': new_fqns,
            'lang': lang, 'module_imports': module_imports, 'tp_imports': tp_imports,
            'css_imports': css_imports, 'html_assets': html_assets}


def _acquire_lock(root, max_wait=10, stale_timeout=60):

    lock_path = os.path.join(root, '.ai-memory', 'knowledge-graph', '.lock')
    for _ in range(max_wait):
        if os.path.isfile(lock_path):
            try:
                age = time.time() - os.path.getmtime(lock_path)
                if age > stale_timeout:
                    break  
            except Exception:
                break
            time.sleep(1)
        else:
            break
    try:
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        with open(lock_path, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except Exception:
        return False


def _release_lock(root):

    lock_path = os.path.join(root, '.ai-memory', 'knowledge-graph', '.lock')
    try:
        if os.path.isfile(lock_path):
            os.remove(lock_path)
    except Exception:
        pass


def build(root):

    out_dir = os.path.join(root, '.ai-memory', 'knowledge-graph')
    _acquire_lock(root)  
    os.makedirs(out_dir, exist_ok=True)
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS
                       and not d.startswith('.')]
        for fn in filenames:
            if fn.endswith(SRC_EXTS):
                files.append(os.path.join(dirpath, fn))
    file_list = [os.path.relpath(p, root).replace(os.sep, '/') for p in files]
    lsp = detect_lsp(root)
    
    CONST_TABLE = {}
    for f, p in sorted(zip(file_list, files)):  
        try:
            txt = read_text(p)
        except Exception:
            continue
        for nm, val in extract_defines(txt, f).items():
            CONST_TABLE[nm] = val  
    extracted = {f: extract_file(p, root, CONST_TABLE) for f, p in zip(file_list, files)}
    COMPOSER = parse_composer(root)

    nodes = {}      
    edges = []      
    edge_keys = set()  
    symbols = {}    
    fqn_symbols = {}  
    dangling = []
    orphan_symbols = []
    include_total = 0
    include_valid = 0

    
    for rel, ex in extracted.items():
        ns = ex['namespace']
        for c in ex['classes']:
            symbols[c['name']] = {'file': rel, 'line': c['line']}
            if ns:
                fqn_symbols[(ns + '\\' + c['name']).lower()] = rel
        nodes[rel] = {'file': rel, 'classes': [c['name'] for c in ex['classes']],
                      'funcs': ex['funcs']}

    def add_edge_if_exists(rel, target_rel, kind, symbol=None):

        nonlocal include_total, include_valid, edge_keys
        
        if os.path.isabs(target_rel):
            normed = os.path.normpath(target_rel)  
            if normed.startswith(os.path.abspath(root)):
                target_rel = os.path.relpath(normed, os.path.abspath(root)).replace(os.sep, '/')
            else:
                return  
        if kind == 'include':
            include_total += 1
        if target_rel and os.path.exists(os.path.join(root, target_rel)):
            if any(d in target_rel.split('/') for d in _EXCLUDE_DIRS):
                return
            if kind == 'include':
                include_valid += 1
            key = (rel, target_rel, kind)
            if key in edge_keys:
                return
            edge_keys.add(key)
            e = {'from': rel, 'to': target_rel, 'kind': kind}
            if symbol:
                e['symbol'] = symbol
            edges.append(e)
        else:
            dangling.append({'from': rel, 'raw': target_rel, 'resolved': target_rel,
                             'base': 'ns' if kind != 'include' else 'src'})

    for rel, ex in extracted.items():
        for c in ex['classes']:
            if c.get('extends'):
                ext = c['extends']
                
                tgt = None
                if '\\' in ext:
                    tgt = fqn_symbols.get(ext.lower()) or fqn_to_file(ext, COMPOSER, root)
                elif ext in symbols:
                    tgt = symbols[ext]['file']
                if tgt:
                    add_edge_if_exists(rel, tgt, 'extends')
        for inc in ex['includes']:
            add_edge_if_exists(rel, inc.replace(os.sep, '/'), 'include')
        
        for u in ex['uses']:
            fqn = u['fqn']
            tgt = fqn_symbols.get(fqn.lower()) or fqn_to_file(fqn, COMPOSER, root)
            if tgt:
                add_edge_if_exists(rel, tgt, 'use', symbol=fqn)
        
        for fqn in ex['new_fqns']:
            tgt = fqn_symbols.get(fqn.lower()) or fqn_to_file(fqn, COMPOSER, root)
            if tgt and tgt != rel:
                add_edge_if_exists(rel, tgt, 'autoload', symbol=fqn)
        
        for func, spec in ex['tp_imports']:
            if func == 'vendor':
                spec = 'Vendor.' + spec  
            tgt = resolve_tp_import(spec, root, CONST_TABLE)
            if tgt and tgt != rel:
                add_edge_if_exists(rel, tgt, 'tpimport', symbol=spec)
        
        if ex['lang']:
            for spec in ex['module_imports']:
                tgt = resolve_module(spec, ex['lang'], rel, root)
                if tgt and tgt != rel:
                    add_edge_if_exists(rel, tgt, 'import', symbol=spec)
        
        for tpl in ex['tpl_includes']:
            trel = os.path.normpath(tpl.lstrip('/'))
            if not (trel.startswith('/') or re.match(r'^[A-Za-z]:', trel)):
                trel = os.path.normpath(os.path.join(os.path.dirname(rel), trel))
            add_edge_if_exists(rel, trel.replace(os.sep, '/'), 'template')
        
        for imp in ex['css_imports']:
            trel = os.path.normpath(os.path.join(os.path.dirname(rel), imp.lstrip('/')))
            add_edge_if_exists(rel, trel.replace(os.sep, '/'), 'cssimport')
        
        for a in ex['html_assets']:
            if a.startswith(('/', 'http://', 'https://', '//', '#', 'data:')):
                continue  
            trel = os.path.normpath(os.path.join(os.path.dirname(rel), a))
            add_edge_if_exists(rel, trel.replace(os.sep, '/'), 'asset')
        for call in ex['calls']:
            
            if call in symbols and symbols[call]['file'] != rel:
                key = (rel, symbols[call]['file'], 'calls')
                if key not in edge_keys:
                    edge_keys.add(key)
                    edges.append({'from': rel, 'to': symbols[call]['file'],
                                  'kind': 'calls', 'symbol': call})

    
    referenced = set()
    for ex in extracted.values():
        for c in ex['classes']:
            if c.get('extends'):
                referenced.add(c['extends'].lstrip('\\').split('\\')[-1].lower())
        for u in ex['uses']:
            referenced.add(u.split('\\')[-1].lower())
        for call in ex['calls']:
            referenced.add(call.lower())
    seen_orphan = set()
    for name, loc in symbols.items():
        short = name.split('\\')[-1].lower()
        if short not in referenced:
            key = (loc['file'], loc.get('line', 0), short)
            if key not in seen_orphan:
                seen_orphan.add(key)
                orphan_symbols.append({'name': name, 'file': loc['file'], 'line': loc.get('line', 0)})

    graph = {'nodes': nodes, 'edges': edges}
    meta = {
        'built_at': __import__('datetime').datetime.now().isoformat(),
        'tool_version': '1.0.0',
        'root': root,
        'file_hashes': {f: file_hash(os.path.join(root, f)) for f in file_list},
        'file_mtimes': {f: _safe_mtime(os.path.join(root, f)) for f in file_list},
        'lsp_available': lsp,
        'accuracy_report': {
            'edges_total': len(edges),
            'edges_valid': len([e for e in edges if os.path.exists(
                os.path.join(root, e['to']))]) if edges else 0,
            'edges_dangling': len(dangling),
            'symbols_total': len(symbols),
            'symbols_resolved': len(symbols),
            'symbols_orphan': len(orphan_symbols),
            'static_coverage': round(include_valid / include_total, 3) if include_total else 1.0,
            'include_total': include_total,
            'include_valid': include_valid,
            'lsp_available': lsp,
        },
        'dangling_edges': dangling,
        'orphan_symbols': orphan_symbols,
        'script_hash': file_hash(os.path.abspath(__file__)),
        
        'composer_hash': file_hash(os.path.join(root, 'composer.json'))
            if os.path.isfile(os.path.join(root, 'composer.json')) else None,
    }
    
    _atomic_write(os.path.join(out_dir, 'graph.json'), graph)
    _atomic_write(os.path.join(out_dir, 'meta.json'), meta)
    _atomic_write(os.path.join(out_dir, 'symbols.json'), symbols)
    _write_markdown(os.path.join(out_dir, 'graph.md'), graph, root)
    print(f"[GRAPH-ACCURACY] 有效边 {meta['accuracy_report']['edges_valid']} / "
          f"悬空 {meta['accuracy_report']['edges_dangling']}（已剔除）/ "
          f"include解析率 {meta['accuracy_report']['static_coverage']} / LSP: "
          f"{','.join(k for k, v in lsp.items() if v) or 'none'}")
    _release_lock(root)
    return graph, meta, symbols


def _atomic_write(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _write_markdown(path, graph, root):

    lines = ['# 项目结构图谱（人类可读兜底，agent 不加载）', '']
    for rel, n in graph['nodes'].items():
        lines.append(f"- {rel}  [classes: {', '.join(n['classes']) or '-'}]")
    lines.append('')
    lines.append('## 边')
    for e in graph['edges']:
        lines.append(f"- {e['from']} --{e['kind']}--> {e['to']}")
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def query(graph, meta, symbols, root, q, direction='both', depth=2, all_cycles=False, max_nodes=80):






    
    entry = None
    if q in graph['nodes']:
        entry = q
    elif q in symbols:
        entry = symbols[q]['file']
    else:
        
        for rel in graph['nodes']:
            if rel.endswith('/' + q) or rel == q:
                entry = rel
                break
    if not entry:
        print(f"[GRAPH-QUERY] 符号索引缺失：{q}（返回空子图，未做全图扫描）")
        return {'nodes': {}, 'edges': [], 'cycle': 0}

    
    adj = {'up': {}, 'down': {}}
    edge_kind_map = {}  
    seen_pair = set()
    for e in graph['edges']:
        key = (e['from'], e['to'])
        if key not in seen_pair:
            seen_pair.add(key)
            if e['to'] not in adj['down'].setdefault(e['from'], []):
                adj['down'][e['from']].append(e['to'])
            if e['from'] not in adj['up'].setdefault(e['to'], []):
                adj['up'][e['to']].append(e['from'])
        edge_kind_map.setdefault(key, [])
        if e['kind'] not in edge_kind_map[key]:
            edge_kind_map[key].append(e['kind'])

    MAX_NODES = max_nodes  
    visited = set()    
    stack = set()      
    subgraph_nodes = {}
    subgraph_edges = []
    cycles = [0]
    seen_cycle = set()  
    
    
    
    
    def _reachable(entry, direction):
        dirs = []
        if direction in ('up', 'both'):
            dirs.append('up')
        if direction in ('down', 'both'):
            dirs.append('down')
        seen = {entry}
        stack = [entry]
        while stack:
            u = stack.pop()
            for dr in dirs:
                for v in adj[dr].get(u, []):
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
        return seen

    def detect_cycles(starts, allowed):
        vis = set(); st = set(); pairs = []
        def dfs(u):
            vis.add(u); st.add(u)
            for v in adj['down'].get(u, []):
                if v not in allowed:      
                    continue
                if v in st:
                    pairs.append((u, v))   
                elif v not in vis:
                    dfs(v)
            st.discard(u)
        for s in starts:
            if s not in vis:
                dfs(s)
        return pairs
    
    if all_cycles:
        cyc_scope = set(graph['nodes'])
    else:
        cyc_scope = _reachable(entry, direction)
    cyc_pairs = detect_cycles(cyc_scope, cyc_scope)
    cyc_set = set(cyc_pairs)
    cycles[0] = len(cyc_pairs)

    def walk(node, d, came_from=None, came_dir=None):
        if node in visited:
            return
        visited.add(node)
        stack.add(node)
        if node in graph['nodes']:
            subgraph_nodes[node] = graph['nodes'][node]
        if d >= depth or len(subgraph_nodes) >= MAX_NODES:
            stack.discard(node)
            return
        dirs = []
        if direction in ('up', 'both'):
            dirs.append('up')
        if direction in ('down', 'both'):
            dirs.append('down')
        for dr in dirs:
            for nxt in adj[dr].get(node, []):
                if len(subgraph_nodes) >= MAX_NODES:
                    return
                
                
                if nxt == came_from and dr != came_dir:
                    continue
                
                
                if nxt in stack and dr == 'down' and (node, nxt) in cyc_set:
                    
                    if nxt in graph['nodes']:
                        subgraph_nodes.setdefault(nxt, graph['nodes'][nxt])
                    if (node, nxt) not in seen_cycle:
                        seen_cycle.add((node, nxt))
                        subgraph_edges.append({'from': node, 'to': nxt,
                                               'kind': 'cycle'})
                    continue
                
                kinds = edge_kind_map.get((node, nxt)) or edge_kind_map.get(
                    (nxt, node)) or ['include']
                for k in kinds:
                    subgraph_edges.append({'from': node, 'to': nxt, 'kind': k})
                walk(nxt, d + 1, came_from=node, came_dir=dr)
        stack.discard(node)

    walk(entry, 0)
    if cycles[0]:
        print(f"[GRAPH-CYCLE] 检测到 {cycles[0]} 个环（已在子图中折叠）")
    return {'nodes': subgraph_nodes, 'edges': subgraph_edges, 'cycle': cycles[0]}


def _graph_files_present(root):

    kg = os.path.join(root, '.ai-memory', 'knowledge-graph')
    return all(os.path.isfile(os.path.join(kg, f))
               for f in ('graph.json', 'meta.json', 'symbols.json'))


def need_rebuild(root):








    meta_path = os.path.join(root, '.ai-memory', 'knowledge-graph', 'meta.json')
    if not os.path.exists(meta_path):
        return True, None
    try:
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
    except Exception:
        return True, None
    changed_files = set()
    current_rels = set()  
    mtimes = meta.get('file_mtimes', {})  
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS
                       and not d.startswith('.')]
        for fn in filenames:
            if fn.endswith(SRC_EXTS):
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, root).replace(os.sep, '/')
                current_rels.add(rel)
                
                if rel in mtimes and mtimes[rel] == _safe_mtime(p):
                    continue
                h = file_hash(p)
                if rel not in meta.get('file_hashes', {}) or meta['file_hashes'][rel] != h:
                    changed_files.add(rel)
    
    if set(meta.get('file_hashes', {})) - current_rels:
        return True, None
    
    if meta.get('script_hash') != file_hash(os.path.abspath(__file__)):
        return True, None
    cj = os.path.join(root, 'composer.json')
    if os.path.isfile(cj):
        if file_hash(cj) != meta.get('composer_hash'):
            return True, None
    elif meta.get('composer_hash') is not None:
        return True, None
    return len(changed_files) > 0, changed_files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=os.getcwd())
    ap.add_argument('--query', help='入口 file 或 symbol，多个逗号分隔合并子图')
    ap.add_argument('--direction', default='both', choices=['up', 'down', 'both'])
    ap.add_argument('--depth', type=int, default=2)
    ap.add_argument('--rebuild', action='store_true', help='强制全量重建')
    ap.add_argument('--no-rebuild', action='store_true',
                    help='跳过新鲜度检测，直接复用已缓存图谱（仅在确认图谱新鲜的连续查询时使用）')
    ap.add_argument('--all-cycles', action='store_true',
                    help='全局环检测：对任意查询都全图 DFS 预警循环依赖（不受 --direction 闭包限制），默认关')
    ap.add_argument('--exclude', default=None,
                    help='追加排除目录（逗号分隔），合并到默认排除 + .graphignore')
    ap.add_argument('--max-nodes', type=int, default=80,
                    help='查询子图节点预算硬上限（默认 80，防枢纽模块爆炸）')
    ap.add_argument('--selftest', action='store_true',
                    help='运行内置 E2E 自检（删文件无悬挂边 + 改文件过期判定），不改交付物')
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    
    _EXCLUDE_DIRS.clear()
    _EXCLUDE_DIRS.update(load_exclude_dirs(root, args.exclude))
    if args.selftest:
        import tempfile as _tf
        import shutil as _shutil
        
        work = _tf.mkdtemp(prefix='kg_selftest_')
        _shutil.copytree(root, work, dirs_exist_ok=True,
                         ignore=_shutil.ignore_patterns('.ai-memory', '.codebuddy', '.git'))
        kg = os.path.join(work, '.ai-memory', 'knowledge-graph')
        def load():
            return (json.load(open(os.path.join(kg, 'graph.json'), encoding='utf-8')),
                    json.load(open(os.path.join(kg, 'meta.json'), encoding='utf-8')),
                    json.load(open(os.path.join(kg, 'symbols.json'), encoding='utf-8')))
        build(work)
        g, m, s = load()
        
        
        
        
        fx_dir = os.path.join(work, '__kg_phantom_fixture__')
        os.makedirs(fx_dir, exist_ok=True)
        fx = os.path.join(fx_dir, 'phantom.php')
        with open(fx, 'w', encoding='utf-8') as _f:
            _f.write(
                "<?php\n"
                "// class KgTestPhantomCls extends RealClass\n"   
                "// KgTestPhantomHelper::go();\n"                 
                "/* class KgTestPhantomDead {} */\n"              
                "class RealClass {}\n"                        
                "function realFunc() {}\n"                    
                "$o = new RealClass();\n"                     
                "RealClass::const();\n"                       
            )
        build(work)
        g5, _, s5 = load()
        phantom_names = ('KgTestPhantomCls', 'KgTestPhantomDead', 'KgTestPhantomHelper')
        
        
        
        fx_rel = '__kg_phantom_fixture__/phantom.php'
        fx_syms = [n for n, loc in s5.items()
                   if isinstance(loc, dict) and loc.get('file') == fx_rel]
        phantom_syms = [n for n in phantom_names if n in fx_syms]
        print('[E2E-5] 伪符号命中:', phantom_syms, '(期望 [])')
        assert not phantom_syms, '[E2E-5] 注释伪符号未过滤: %s' % phantom_syms
        
        
        
        assert 'RealClass' in fx_syms, '[E2E-5] fixture 真实符号 RealClass 被误剥（fx_syms 缺失）'
        
        phantom_edges = [e for e in g5['edges']
                         if e.get('symbol') in phantom_names]
        print('[E2E-5] 指向伪符号的假边:', len(phantom_edges), '(期望 0)')
        assert not phantom_edges, '[E2E-5] 存在指向注释伪符号的假边'
        print('[E2E-5] 通过：注释伪符号已过滤，真实符号保留')
        
        _s6_in = (
            "<?php\n"
            "class A {}\n"        
            "/* multi\n"          
            "   line comment\n"    
            "*/\n"                
            "class B {}\n"        
        )
        _s6_out = strip_php_comments(_s6_in)
        _s6_nl_in = _s6_in.count('\n')
        _s6_nl_out = _s6_out.count('\n')
        print('[E2E-6] 换行数 输入/输出:', _s6_nl_in, '/', _s6_nl_out, '(期望相等)')
        assert _s6_nl_out == _s6_nl_in, \
            '[E2E-6] 块注释删除内部换行致行号位移：去 %d 行' % (_s6_nl_in - _s6_nl_out)
        assert 'class B' in _s6_out, '[E2E-6] 真实符号 B 被块注释误吞'
        print('[E2E-6] 通过：块注释内部换行已保留，行号不位移')
        
        _py_f = os.path.join(work, '__kg_lang_iso__.py')
        with open(_py_f, 'w', encoding='utf-8') as _f:
            _f.write("class FakeCls:\n    x = new RealCls()\n")
        _js_f = os.path.join(work, '__kg_lang_iso__.js')
        with open(_js_f, 'w', encoding='utf-8') as _f:
            _f.write("class KgTestPhantomCls { go() { this.helper() } }\n")
        _php_f = os.path.join(work, '__kg_lang_iso__.php')
        with open(_php_f, 'w', encoding='utf-8') as _f:
            _f.write("<?php\nclass RealPhpCls {}\n")
        _ex_py = extract_file(_py_f, work)
        _ex_js = extract_file(_js_f, work)
        _ex_php = extract_file(_php_f, work)
        _py_classes = [c['name'] for c in _ex_py['classes']]
        _js_classes = [c['name'] for c in _ex_js['classes']]
        print('[E2E-7] .py 误抽 class:', _py_classes, '(期望 [])')
        print('[E2E-7] .js 误抽 class:', _js_classes, '(期望 [])')
        assert not _py_classes, '[E2E-7] .py 被误抽 PHP 符号: %s' % _py_classes
        assert not _js_classes, '[E2E-7] .js 被误抽 PHP 符号: %s' % _js_classes
        
        _php_classes = [c['name'] for c in _ex_php['classes']]
        assert 'RealPhpCls' in _php_classes, \
            '[E2E-7] PHP 真实类未被抽取（门禁误伤）: %s' % _php_classes
        print('[E2E-7] 通过：非 PHP 零误抽，PHP 抽取保留')
        
        
        
        def _mk_g(nodes, edges):
            return {'nodes': {n: {} for n in nodes},
                    'edges': [{'from': a, 'to': b, 'kind': 'include'} for a, b in edges]}
        _cyc_cases = [
            
            ('菱形DAG(both)', ['A', 'B', 'C', 'D'],
             [('A', 'B'), ('A', 'C'), ('B', 'D'), ('C', 'D')], 'both', 0),   
            ('真实3环(both)', ['A', 'B', 'C'],
             [('A', 'B'), ('B', 'C'), ('C', 'A')], 'both', 1),                
            ('互环2(both)', ['A', 'B'],
             [('A', 'B'), ('B', 'A')], 'both', 1),                            
            ('自环(both)', ['A'], [('A', 'A')], 'both', 1),                   
            ('平行边(both)', ['A', 'B'],
             [('A', 'B'), ('A', 'B')], 'both', 0),                            
            ('真实3环(up)', ['A', 'B', 'C'],
             [('A', 'B'), ('B', 'C'), ('C', 'A')], 'up', 1),                  
            ('上游环(up)', ['X', 'Y', 'Z'],
             [('Y', 'X'), ('Y', 'Z'), ('Z', 'Y')], 'up', 1),                  
        ]
        for _cn, _nd, _ed, _dir, _exp in _cyc_cases:
            _gr = _mk_g(_nd, _ed)
            _r = query(_gr, {}, {}, work, _nd[0], direction=_dir, depth=5)
            print('[E2E-8] %s 环数: %s (期望 %s)' % (_cn, _r['cycle'], _exp))
            assert _r['cycle'] == _exp, \
                '[E2E-8] %s 环数=%s 期望 %s（守恒违反）' % (_cn, _r['cycle'], _exp)
        print('[E2E-8] 通过：环检测三守恒（不重不漏/方向一致/平行边不翻倍）均满足')
        
        
        _g9 = _mk_g(['A', 'B', 'X'], [('A', 'B'), ('B', 'A'), ('A', 'X')])
        _r9_def = query(_g9, {}, {}, work, 'X', direction='down', depth=5, all_cycles=False)
        print('[E2E-9] 默认(down,entry=X) 环数: %s (期望 0)' % _r9_def['cycle'])
        assert _r9_def['cycle'] == 0, '[E2E-9] 默认模式误报闭包外环: %s' % _r9_def['cycle']
        _r9_all = query(_g9, {}, {}, work, 'X', direction='down', depth=5, all_cycles=True)
        print('[E2E-9] 全局(--all-cycles,down,entry=X) 环数: %s (期望 1)' % _r9_all['cycle'])
        assert _r9_all['cycle'] == 1, '[E2E-9] 全局模式漏报全图环: %s' % _r9_all['cycle']
        print('[E2E-9] 通过：全局环检测开关生效且不破坏默认闭包行为')
        
        victim = None
        for e in g['edges']:
            if e['kind'] == 'include' and os.path.exists(os.path.join(work, e['to'])):
                victim = e['to']
                break
        if not victim:
            
            
            _shutil.rmtree(work)
            print('[SELFTEST] 跳过 E2E-3/4：当前目录图谱无 include 边（非 PHP/JS include 项目），无法构造 victim（副本已清理）')
            return
        dependents = [e['from'] for e in g['edges'] if e['to'] == victim]
        print('[E2E-3] 依赖', victim, '的文件数:', len(dependents))
        bak = os.path.join(work, victim) + '.baktest'
        os.rename(os.path.join(work, victim), bak)
        build(work)
        g2, _, _ = load()
        hanging = [e for e in g2['edges'] if e['to'] == victim]
        print('[E2E-3] 删除后悬挂边:', len(hanging), '(期望 0)')
        os.rename(bak, os.path.join(work, victim))
        
        orig = open(os.path.join(work, victim), encoding='utf-8', errors='ignore').read()
        open(os.path.join(work, victim), 'a', encoding='utf-8').write('\n// e2e touch\n')
        stale, changed_info = need_rebuild(work)
        cnt = len(changed_info) if changed_info else '全量'
        print('[E2E-4] 编辑后过期:', stale, '变更文件数:', cnt, '(期望 True/>0)')
        open(os.path.join(work, victim), 'w', encoding='utf-8').write(orig)
        _shutil.rmtree(work)
        print('[SELFTEST] 完成（副本已清理，原交付物未改动）')
        return
    kg_dir = os.path.join(root, '.ai-memory', 'knowledge-graph')

    
    if args.rebuild:
        build(root)
        return
    if args.query:
        if args.no_rebuild and _graph_files_present(root):
            print('[GRAPH-USED-CACHE] 跳过新鲜度检测，复用已缓存图谱')
        else:
            stale, changed_info = need_rebuild(root)
            
            
            if stale or not _graph_files_present(root):
                if changed_info:
                    preview = ', '.join(sorted(changed_info)[:5])
                    suffix = '…' if len(changed_info) > 5 else ''
                    print(f"[GRAPH-STALE] {len(changed_info)} 个文件变更：{preview}{suffix}，正在重建…")
                else:
                    print("[GRAPH-STALE] 图谱过期（产物缺失/脚本升级/composer.json 变更），正在全量重建…")
                build(root)  
            else:
                print("[GRAPH-FRESH] 图谱新鲜")
        with open(os.path.join(kg_dir, 'graph.json'), encoding='utf-8') as f:
            graph = json.load(f)
        with open(os.path.join(kg_dir, 'meta.json'), encoding='utf-8') as f:
            meta = json.load(f)
        with open(os.path.join(kg_dir, 'symbols.json'), encoding='utf-8') as f:
            symbols = json.load(f)
        
        
        merged = {'nodes': {}, 'edges': [], 'cycle': 0}
        for q in args.query.split(','):
            q = q.strip()
            if not q:
                continue
            sub = query(graph, meta, symbols, root, q, args.direction, args.depth,
                        args.all_cycles, args.max_nodes)
            merged['nodes'].update(sub['nodes'])
            merged['edges'].extend(sub['edges'])
            merged['cycle'] += sub['cycle']
        print(json.dumps(merged, ensure_ascii=False))
        return
    
    build(root)


if __name__ == '__main__':
    main()
