#!/usr/bin/env python3

import subprocess, os, json

CJK_FONT_PRIORITY = [
    
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    
    "C:/Windows/Fonts/msyh.ttc",       
    "C:/Windows/Fonts/simhei.ttf",      
    "C:/Windows/Fonts/simsun.ttc",      
    
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]

def detect_cjk_font():

    for p in CJK_FONT_PRIORITY:
        if os.path.exists(p):
            return p
    
    try:
        result = subprocess.run(
            ["fc-list", ":lang=zh", "file"],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            
            for line in result.stdout.strip().split('\n'):
                if ':' in line:
                    return line.split(':')[0].strip()
    except Exception:
        pass
    return None

if __name__ == "__main__":
    font = detect_cjk_font()
    if font:
        print(json.dumps({"found": True, "path": font, "name": os.path.basename(font)}))
    else:
        print(json.dumps({"found": False, "path": None}))
