#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容入口：等同 check_chapter_wordcount.py --platform tomato"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name('check_chapter_wordcount.py')

if __name__ == '__main__':
    args = [sys.executable, str(SCRIPT)] + sys.argv[1:]
    if '--platform' not in sys.argv:
        if len(sys.argv) >= 2 and sys.argv[1] == '--all':
            args = [sys.executable, str(SCRIPT), '--all', sys.argv[2], '--platform', 'tomato'] + sys.argv[3:]
        elif len(sys.argv) >= 2:
            args = [sys.executable, str(SCRIPT), sys.argv[1], '--platform', 'tomato'] + sys.argv[2:]
    sys.exit(subprocess.call(args))
