#!/usr/bin/env python3
# -*- coding: utf-8 -*-








import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

SKIP_DIRS = {".git", "node_modules", "target", "build", "dist", ".idea", ".vscode",
             "__pycache__", ".venv", "venv", "out", ".gradle", ".mvn", "bin", "obj",
             ".next", "coverage", ".tox", ".eggs"}

CODE_EXT = {".java": "java", ".kt": "kotlin", ".py": "python", ".js": "javascript",
            ".ts": "typescript", ".jsx": "javascript", ".tsx": "typescript",
            ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
            ".cs": "csharp", ".c": "c", ".cpp": "cpp", ".h": "c",
            ".scala": "scala", ".vue": "vue", ".sh": "shell"}

BUILD_FILES = {
    "pom.xml": "maven", "build.gradle": "gradle", "build.gradle.kts": "gradle",
    "package.json": "npm", "pnpm-lock.yaml": "npm", "yarn.lock": "npm",
    "requirements.txt": "pip", "pyproject.toml": "pip", "setup.py": "pip",
    "go.mod": "go", "Cargo.toml": "cargo", "Gemfile": "ruby",
    "composer.json": "composer", "CMakeLists.txt": "cmake",
}


SPRING_ANN = ["SpringBootApplication", "Configuration", "Bean", "Component", "Service",
              "Repository", "Controller", "RestController", "Autowired", "Qualifier",
              "Primary", "Value", "Resource", "Inject", "Profile", "Scope",
              "ConditionalOnClass", "ConditionalOnProperty", "ConditionalOnMissingBean",
              "ConfigurationProperties", "EnableAutoConfiguration", "Import",
              "ComponentScan", "Lazy", "DependsOn", "Transactional", "RequestMapping",
              "GetMapping", "PostMapping", "Aspect", "Scheduled"]

INJECT_ANN = ("Autowired", "Resource", "Inject")


def read_lines(path, limit=4000):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.readlines()[:limit]
    except Exception:
        return []


def strip_comments(text):

    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(ln for ln in text.splitlines()
                     if not ln.strip().startswith(("//", "*")))


def detect_build(root):
    found = []
    for bf, kind in BUILD_FILES.items():
        p = os.path.join(root, bf)
        if os.path.exists(p):
            found.append({"file": bf, "kind": kind})
    for d in sorted(os.listdir(root))[:80]:
        sub = os.path.join(root, d)
        if os.path.isdir(sub) and d not in SKIP_DIRS:
            for bf, kind in BUILD_FILES.items():
                if os.path.exists(os.path.join(sub, bf)):
                    found.append({"file": f"{d}/{bf}", "kind": kind})
    return found


def parse_maven(path):
    deps, props = [], {}
    txt = "".join(read_lines(path, 6000))
    for m in re.finditer(r"<([\w.\-]+)>([^<]*)</\1>", txt):
        if m.group(1).endswith(".version"):
            props[m.group(1)] = m.group(2).strip()
    parent = re.search(r"<parent>\s*<groupId>([^<]+)</groupId>\s*"
                       r"<artifactId>([^<]+)</artifactId>\s*"
                       r"<version>([^<]+)</version>", txt)
    for m in re.finditer(
            r"<dependency>(.*?)</dependency>", txt, re.S):
        blk = m.group(1)
        g = re.search(r"<groupId>([^<]+)</groupId>", blk)
        a = re.search(r"<artifactId>([^<]+)</artifactId>", blk)
        v = re.search(r"<version>([^<]+)</version>", blk)
        s = re.search(r"<scope>([^<]+)</scope>", blk)
        if g and a:
            ver = v.group(1).strip() if v else ""
            if ver.startswith("${") and ver.endswith("}"):
                ver = props.get(ver[2:-1], ver)
            deps.append({"group": g.group(1).strip(), "artifact": a.group(1).strip(),
                         "version": ver, "scope": (s.group(1).strip() if s else "compile")})
    return {
        "parent": (f"{parent.group(1)}:{parent.group(2)}:{parent.group(3)}"
                   if parent else None),
        "dependencies": deps,
    }


def parse_gradle(path):
    deps = []
    for i, ln in enumerate(read_lines(path, 3000), 1):
        m = re.search(r"""(implementation|api|compile|testImplementation|runtimeOnly)\s*[\s('"]+
                      ([\w.\-]+):([\w.\-]+):?([\w.\-]+)?""", ln, re.X)
        if m:
            deps.append({"group": m.group(2), "artifact": m.group(3),
                         "version": m.group(4) or "", "scope": m.group(1), "line": i})
    return {"dependencies": deps}


def parse_package_json(path):
    try:
        d = json.loads("".join(read_lines(path, 3000)))
    except Exception:
        return {"dependencies": []}
    out = []
    for sec in ("dependencies", "devDependencies", "peerDependencies"):
        for k, v in (d.get(sec) or {}).items():
            out.append({"group": "", "artifact": k, "version": v, "scope": sec})
    return {"dependencies": out, "entry": d.get("main"), "scripts": d.get("scripts")}


def parse_requirements(path):
    out = []
    for i, ln in enumerate(read_lines(path, 3000), 1):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        m = re.match(r"([\w\-\.\[\]]+)\s*([=<>!~]+)?\s*([\w\.\-\*]+)?", ln)
        if m:
            out.append({"group": "", "artifact": m.group(1),
                        "version": m.group(3) or "", "scope": "runtime", "line": i})
    return {"dependencies": out}


def parse_dependencies(root):
    result, files = [], []
    for root_dir, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in fs:
            if f == "pom.xml":
                r = parse_maven(os.path.join(root_dir, f))
                files.append(os.path.relpath(os.path.join(root_dir, f), root))
                for d in r["dependencies"]:
                    d["source"] = os.path.relpath(os.path.join(root_dir, f), root)
                result += r["dependencies"]
                if r.get("parent"):
                    result.append({"group": "parent", "artifact": r["parent"],
                                   "version": "", "scope": "parent", "source": f})
            elif f in ("build.gradle", "build.gradle.kts"):
                r = parse_gradle(os.path.join(root_dir, f))
                files.append(os.path.relpath(os.path.join(root_dir, f), root))
                result += r["dependencies"]
            elif f == "package.json":
                r = parse_package_json(os.path.join(root_dir, f))
                files.append(os.path.relpath(os.path.join(root_dir, f), root))
                result += r["dependencies"]
            elif f in ("requirements.txt",):
                r = parse_requirements(os.path.join(root_dir, f))
                files.append(os.path.relpath(os.path.join(root_dir, f), root))
                result += r["dependencies"]
    return result, sorted(set(files))


def find_entry_points(root, lang):

    entries = []
    for root_dir, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in fs:
            p = os.path.join(root_dir, f)
            ext = os.path.splitext(f)[1]
            rel = os.path.relpath(p, root)
            if ext == ".java":
                lines = read_lines(p)
                for i, ln in enumerate(lines, 1):
                    idx = i - 1          
                    if "public static void main" in ln:
                        cls = None
                        for j in range(max(0, idx - 25), idx + 1):
                            m = re.search(r"(?:class|interface)\s+(\w+)", lines[j])
                            if m:
                                cls = m.group(1)
                        ann = []
                        for j in range(max(0, idx - 25), idx + 1):
                            a = re.search(r"@(\w+)", lines[j])
                            if a:
                                ann.append(a.group(1))
                        entries.append({"file": rel, "line": i,
                                        "symbol": cls or f, "kind": "java-main",
                                        "annotations": ann[-3:]})
                    elif "@SpringBootApplication" in ln \
                            and not ln.strip().startswith(("*", "//")):
                        cls = None
                        for j in range(idx, min(len(lines), idx + 8)):
                            m = re.search(r"class\s+(\w+)", lines[j])
                            if m:
                                cls = m.group(1)
                                break
                        entries.append({"file": rel, "line": i,
                                        "symbol": cls or f, "kind": "spring-boot",
                                        "annotations": ["SpringBootApplication"]})
            elif f == "__main__.py":
                entries.append({"file": rel, "line": 1, "symbol": "__main__",
                                "kind": "python-main", "annotations": []})
            elif ext == ".go":
                for i, ln in enumerate(read_lines(p), 1):
                    if re.match(r"func\s+main\s*\(", ln):
                        entries.append({"file": rel, "line": i, "symbol": "main",
                                        "kind": "go-main", "annotations": []})

    
    seen = {}
    for e in entries:
        key = (e["file"], e["symbol"])
        if key not in seen or e["kind"] == "spring-boot":
            seen[key] = e
    return list(seen.values())


def analyze_spring(root):

    ann_counter = Counter()
    inject = {"field": [], "constructor": [], "setter": []}
    beans, configs = [], []

    for root_dir, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in fs:
            if not f.endswith(".java"):
                continue
            p = os.path.join(root_dir, f)
            rel = os.path.relpath(p, root)
            lines = read_lines(p)
            cls_name = os.path.splitext(f)[0]

            
            
            full = "".join(lines)
            code = strip_comments(full)   
            if re.search(r"@(Component|Service|Repository|Controller|RestController"
                         r"|Configuration)\b", code):
                
                for cm in re.finditer(
                        r"(?:^|\n)[ \t]*(?:public|protected|private)?\s*(\w+)\s*"
                        r"\(((?:[^()]|\([^()]*\))*)\)\s*\{", code):
                    cname, params = cm.group(1), cm.group(2).strip()
                    if not params:
                        continue
                    if not re.search(rf"\b(?:class|record)\s+{re.escape(cname)}\b", code):
                        continue
                    before = code[:cm.start()].rstrip().splitlines()
                    prev = before[-1] if before else ""
                    has_ann = bool(re.search(r"@(Autowired|Resource|Inject)\b", prev))
                    n_ctor = len(re.findall(
                        rf"(?:^|\n)[ \t]*(?:public|protected|private)?\s*"
                        rf"{re.escape(cname)}\s*\(", code))
                    if not has_ann and n_ctor == 1:
                        inject["constructor"].append({
                            "file": rel,
                            "line": code[:cm.start()].count("\n") + 1,
                            "annotation": "(implicit 单构造器自动注入)",
                            "params": params[:70]})

            for i, ln in enumerate(lines):
                s0 = ln.strip()
                if s0.startswith(("//", "*", "/*")):
                    continue      
                for a in SPRING_ANN:
                    if re.search(r"@" + a + r"\b", ln):
                        ann_counter[a] += 1
                        if a in ("Component", "Service", "Repository",
                                 "Controller", "RestController"):
                            beans.append({"file": rel, "line": i + 1,
                                          "stereotype": "@" + a, "name": cls_name})
                        if a == "Bean":
                            m = None
                            for j in range(i, min(len(lines), i + 4)):
                                m = re.search(r"(\w+)\s+(\w+)\s*\(", lines[j])
                                if m and m.group(2) != "return":
                                    break
                            beans.append({"file": rel, "line": i + 1,
                                          "stereotype": "@Bean",
                                          "name": m.group(2) if m else "?"})
                        if a == "Configuration":
                            configs.append({"file": rel, "line": i + 1})
                
                if any(re.search(r"@" + a + r"\b", ln) for a in INJECT_ANN):
                    ann_name = next((a for a in INJECT_ANN
                                     if re.search(r"@" + a + r"\b", ln)), "Autowired")
                    for j in range(i + 1, min(len(lines), i + 5)):
                        s = lines[j].strip()
                        if not s or s.startswith("@") or s.startswith("//") \
                                or s.startswith("*"):
                            continue
                        if re.match(r"^[A-Z]\w*\s*\(", s) or \
                                re.match(rf"^(public|protected)?\s*{cls_name}\s*\(", s):
                            inject["constructor"].append(
                                {"file": rel, "line": i + 1, "annotation": "@" + ann_name})
                        elif s.startswith("void set") or re.match(r"^public\s+void\s+set", s):
                            inject["setter"].append(
                                {"file": rel, "line": i + 1, "annotation": "@" + ann_name})
                        elif re.match(r"^(private|protected|public)\s", s) and ";" in s:
                            tn = re.match(r"^(?:private|protected|public)\s+"
                                          r"(?:final\s+|static\s+)?([\w<>\[\],\s.]+?)\s+"
                                          r"(\w+)\s*;", s)
                            inject["field"].append({
                                "file": rel, "line": i + 1, "annotation": "@" + ann_name,
                                "type": tn.group(1).strip() if tn else "?",
                                "name": tn.group(2) if tn else "?"})
                        break
    return {
        "annotation_counts": dict(ann_counter.most_common()),
        "injection": {k: len(v) for k, v in inject.items()},
        "injection_detail": inject,
        "bean_count": len(beans),
        "beans": beans[:60],
        "config_classes": configs[:20],
    }


def scan(root, max_depth=6, top=12):
    root = os.path.abspath(root)
    stats = defaultdict(lambda: {"files": 0, "lines": 0})
    dir_files = defaultdict(int)
    config_files, all_files = [], []

    for root_dir, dirs, fs in os.walk(root):
        depth = root_dir[len(root):].count(os.sep)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if depth > max_depth:
            dirs[:] = []      
        rel_dir = os.path.relpath(root_dir, root)
        for f in fs:
            ext = os.path.splitext(f)[1].lower()
            rel = os.path.relpath(os.path.join(root_dir, f), root)
            all_files.append(rel)
            if ext in CODE_EXT:
                lang = CODE_EXT[ext]
                n = sum(1 for _ in open(os.path.join(root_dir, f),
                                        encoding="utf-8", errors="ignore"))
                stats[lang]["files"] += 1
                stats[lang]["lines"] += n
                dir_files[rel_dir if rel_dir != "." else "(root)"] += 1
            if ext in (".yml", ".yaml", ".properties", ".toml", ".ini", ".env",
                       ".json", ".xml") and depth <= 3:
                config_files.append(rel)

    builds = detect_build(root)
    deps, build_files = parse_dependencies(root)
    lang = (max(stats.items(), key=lambda kv: kv[1]["lines"])[0]
            if stats else "unknown")
    entries = find_entry_points(root, lang)

    result = {
        "path": root,
        "project_types": sorted({b["kind"] for b in builds}),
        "build_files": build_files,
        "main_language": lang,
        "code_stats": {k: v for k, v in sorted(
            stats.items(), key=lambda kv: -kv[1]["lines"])},
        "total_files": len(all_files),
        "top_dirs": [{"dir": d, "code_files": n} for d, n in
                     sorted(dir_files.items(), key=lambda kv: -kv[1])[:top]],
        "dependencies": deps[:120],
        "dependency_count": len(deps),
        "entry_points": entries[:30],
        "config_files": sorted(set(config_files))[:30],
    }

    
    dep_blob = " ".join(d["artifact"].lower() for d in deps).lower()
    fw = []
    if "spring-boot" in dep_blob or "spring-boot" in dep_blob:
        fw.append("spring-boot")
    if any(a["annotations"] and "SpringBootApplication" in a["annotations"]
           for a in entries if a["kind"] == "spring-boot"):
        fw.append("spring-boot")
    if "spring-context" in dep_blob or "spring-core" in dep_blob:
        fw.append("spring-framework")
    if "mybatis" in dep_blob:
        fw.append("mybatis")
    if "hibernate" in dep_blob or "spring-data-jpa" in dep_blob:
        fw.append("jpa/hibernate")
    if "react" in dep_blob:
        fw.append("react")
    if "vue" in dep_blob:
        fw.append("vue")
    if "django" in dep_blob:
        fw.append("django")
    if "flask" in dep_blob:
        fw.append("flask")
    if "fastapi" in dep_blob:
        fw.append("fastapi")
    if "torch" in dep_blob or "tensorflow" in dep_blob:
        fw.append("ml-framework")
    result["frameworks"] = sorted(set(fw))

    if "spring" in " ".join(result["frameworks"]):
        result["spring"] = analyze_spring(root)

    return result


def main():
    ap = argparse.ArgumentParser(description="开源项目扫描器")
    ap.add_argument("path", help="项目根目录")
    ap.add_argument("-o", "--output", help="输出 JSON（不填则只打印摘要）")
    ap.add_argument("--top", type=int, default=12, help="Top N 目录")
    ap.add_argument("--max-depth", type=int, default=6)
    a = ap.parse_args()

    if not os.path.isdir(a.path):
        sys.stderr.write(f"[错误] 目录不存在: {a.path}\n")
        sys.exit(1)

    r = scan(a.path, a.max_depth, a.top)

    print("=" * 62)
    print(f"项目扫描 · {os.path.basename(r['path'])}")
    print("=" * 62)
    print(f"路径        : {r['path']}")
    print(f"主语言      : {r['main_language']}")
    print(f"构建类型    : {', '.join(r['project_types']) or '未识别'}")
    print(f"框架        : {', '.join(r['frameworks']) or '未识别'}")
    print(f"文件总数    : {r['total_files']}")
    print("代码分布    : " + "、".join(
        f"{k} {v['files']}文件/{v['lines']}行" for k, v in list(r["code_stats"].items())[:5]))
    print(f"依赖数量    : {r['dependency_count']}")
    print(f"入口        : {len(r['entry_points'])} 个")
    for e in r["entry_points"][:5]:
        print(f"   {e['kind']:12s} {e['file']}:{e['line']}  {e['symbol']}")
    print("主要目录    : " + "、".join(
        f"{d['dir']}({d['code_files']})" for d in r["top_dirs"][:8]))
    if "spring" in r:
        s = r["spring"]
        print("-" * 62)
        print(f"Spring Bean : {s['bean_count']} 个 | 配置类 {len(s['config_classes'])} 个")
        top_ann = list(s["annotation_counts"].items())[:8]
        print("注解统计    : " + "、".join(f"@{k}×{v}" for k, v in top_ann))
        inj = s["injection"]
        print(f"注入方式    : 字段 {inj['field']} / 构造器 {inj['constructor']} "
              f"/ setter {inj['setter']}")
        if inj["field"] and not inj["constructor"]:
            print("  [提示] 全部为字段注入，存在可测试性与循环依赖隐患，"
                  "建议关注踩坑点章节")
    print("=" * 62)

    if a.output:
        os.makedirs(os.path.dirname(os.path.abspath(a.output)) or ".", exist_ok=True)
        with open(a.output, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        print(f"[OK] 已写出: {a.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
