






from __future__ import annotations

import multiprocessing
import sys


def _bootstrap() -> int:
    
    
    multiprocessing.freeze_support()

    from my_agent.__main__ import main

    return main()


if __name__ == "__main__":
    sys.exit(_bootstrap())
