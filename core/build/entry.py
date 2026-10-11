"""PyInstaller 的入口脚本。

单独放一个入口而不是直接拿 ``my_agent/__main__.py``：PyInstaller 会把入口脚本
当作 ``__main__`` 运行，用包内文件当入口容易和 ``-m`` 的语义混淆。
这里只做一件事——把控制权交给 ``my_agent.__main__.main``。
"""

from __future__ import annotations

import multiprocessing
import sys


def _bootstrap() -> int:
    # PyInstaller 冻结后子进程会用 sys.executable 重新拉起自己，
    # 不调用这个的话，任何使用 multiprocessing 的第三方库都会无限自我复制。
    multiprocessing.freeze_support()

    from my_agent.__main__ import main

    return main()


if __name__ == "__main__":
    sys.exit(_bootstrap())
