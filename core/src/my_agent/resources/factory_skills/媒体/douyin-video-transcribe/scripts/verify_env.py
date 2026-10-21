#!/usr/bin/env python3












import os
import sys
import json
import subprocess
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
VENV_DIR = SKILL_DIR / "venv"
CONFIG_FILE = SKILL_DIR / ".env_config.json"



def find_venv_python() -> str | None:

    
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
            path = cfg.get("venv_python", "")
            if path and os.path.exists(path):
                return path
        except Exception:
            pass

    
    if sys.platform == "win32":
        py = VENV_DIR / "Scripts" / "python.exe"
    else:
        py = VENV_DIR / "bin" / "python"

    if py.exists():
        return str(py)

    return None


def run_python(script: str, timeout: int = 30) -> tuple[int, str, str]:

    python = find_venv_python()
    if not python:
        return -1, "", "venv Python not found"
    try:
        r = subprocess.run(
            [python, "-c", script],
            capture_output=True, text=True, timeout=timeout
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def check_import(pkg: str, attr: str | None = None) -> dict:

    if attr:
        script = f"import {pkg}; print({attr})"
    else:
        script = f"import {pkg}; print('OK')"

    code, out, err = run_python(script, timeout=15)
    return {
        "name": pkg,
        "ok": code == 0,
        "detail": out if code == 0 else (err[:200] if err else "import failed"),
    }


def check_chromium() -> dict:

    
    import platform
    if platform.system() == "Windows":
        base = os.path.expandvars("%USERPROFILE%\\AppData\\Local\\ms-playwright")
    elif platform.system() == "Darwin":
        base = os.path.expanduser("~/Library/Caches/ms-playwright")
    else:
        base = os.path.expanduser("~/.cache/ms-playwright")

    if not os.path.exists(base):
        return {"name": "chromium", "ok": False, "detail": f"未安装 (目录不存在: {base})"}

    
    for item in os.listdir(base):
        if item.startswith("chromium-"):
            if platform.system() == "Windows":
                chrome_exe = os.path.join(base, item, "chrome-win64", "chrome.exe")
            elif platform.system() == "Darwin":
                chrome_exe = os.path.join(base, item, "chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium")
            else:
                chrome_exe = os.path.join(base, item, "chrome-linux64", "chrome")
            if os.path.exists(chrome_exe):
                return {"name": "chromium", "ok": True, "detail": item}
    return {"name": "chromium", "ok": False, "detail": "目录存在但无 chrome 可执行文件"}


def check_whisper_cache() -> dict:

    cache_dir = os.path.expanduser("~/.cache/whisper")
    if not os.path.exists(cache_dir):
        return {"name": "whisper-cache", "ok": False, "detail": "未下载 (目录不存在)"}

    models = [f for f in os.listdir(cache_dir) if f.endswith(".pt")]
    if not models:
        return {"name": "whisper-cache", "ok": False, "detail": "未下载 (无模型文件)"}

    
    ok = []
    suspect = []
    for m in models:
        size = os.path.getsize(os.path.join(cache_dir, m))
        if m == "medium.pt" and size < 500_000_000:
            suspect.append(f"{m} ({size/1024/1024:.0f}MB, 疑似损坏)")
        else:
            ok.append(f"{m} ({size/1024/1024:.0f}MB)")

    if suspect:
        return {"name": "whisper-cache", "ok": False, "detail": f"损坏: {', '.join(suspect)}"}
    return {"name": "whisper-cache", "ok": True, "detail": ", ".join(ok)}




def main():
    json_mode = "--json" in sys.argv
    fix_mode = "--fix" in sys.argv

    if not json_mode:
        print("=" * 50)
        print("  douyin-video-transcribe env check")
        print("=" * 50)
        print()

    
    python_path = find_venv_python()
    if not python_path:
        msg = "venv not found, run scripts/setup_env.py first"
        if json_mode:
            json.dump({"status": "fail", "reason": msg, "checks": []}, sys.stdout, indent=2)
            sys.exit(1)
        
        if fix_mode:
            print(f"  [FAIL] {msg}")
            print("  --fix: auto-running setup_env.py ...")
            setup_script = SKILL_DIR / "scripts" / "setup_env.py"
            result = subprocess.run(
                [sys.executable, str(setup_script), "--force"],
                capture_output=False,
                timeout=600,
            )
            print()
            if result.returncode == 0:
                print("  [SUCCESS] Setup completed. Re-run verify to confirm.")
            else:
                print("  [FAIL] Setup failed with exit code", result.returncode)
            sys.exit(result.returncode)
        else:
            print(f"\033[31m[FAIL]\033[0m {msg}")
            sys.exit(1)

    if not json_mode:
        print(f"  Python: {python_path}")
        print()

    
    checks = []

    
    packages = [
        ("torch", "torch.__version__"),
        ("whisper", None),
        ("playwright", None),
        ("requests", "requests.__version__"),
        ("imageio_ffmpeg", "imageio_ffmpeg.get_ffmpeg_exe()"),
    ]

    all_ok = True
    for pkg, attr in packages:
        result = check_import(pkg, attr)
        checks.append(result)
        if not result["ok"]:
            all_ok = False
        if not json_mode:
            icon = "[OK]" if result["ok"] else "[FAIL]"
            print(f"  {icon} {pkg:20s} {result['detail']}")

    
    chromium = check_chromium()
    checks.append(chromium)
    if not chromium["ok"]:
        all_ok = False
    if not json_mode:
        icon = "[OK]" if chromium["ok"] else "[FAIL]"
        print(f"  {icon} {'chromium':20s} {chromium['detail']}")

    
    cache = check_whisper_cache()
    checks.append(cache)
    
    if not json_mode:
        icon = "[OK]" if cache["ok"] else "[N/A]"
        print(f"  {icon} {'whisper-cache':20s} {cache['detail']}")

    
    if json_mode:
        output = {
            "status": "pass" if all_ok else "fail",
            "python": python_path,
            "checks": checks,
        }
        json.dump(output, sys.stdout, indent=2, ensure_ascii=False)
        sys.exit(0 if all_ok else 1)

    
    print()
    if all_ok:
        print("  [SUCCESS] Environment ready!")
        sys.exit(0)

    
    print("  [FAILURE] Issues found, see [FAIL] marks above")
    print()
    print("  Fix suggestions:")
    for c in checks:
        if not c["ok"]:
            print(f"    - {c['name']}: {c['detail']}")

    
    if fix_mode:
        print()
        print("  --fix: auto-running setup_env.py --force ...")
        setup_script = SKILL_DIR / "scripts" / "setup_env.py"
        if not setup_script.exists():
            print("  [FAIL] setup_env.py not found at", setup_script)
            sys.exit(1)
        
        result = subprocess.run(
            [sys.executable, str(setup_script), "--force"],
            capture_output=False,
            timeout=600,
        )
        print()
        if result.returncode == 0:
            print("  [SUCCESS] Auto-fix completed. Re-run verify to confirm.")
        else:
            print("  [FAIL] Auto-fix failed with exit code", result.returncode)
        sys.exit(result.returncode)
    else:
        print()
        print("  Auto-fix: python scripts/setup_env.py --force")
        print("           or: python scripts/verify_env.py --fix")
        sys.exit(1)


if __name__ == "__main__":
    main()
