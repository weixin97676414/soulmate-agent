# -*- coding: utf-8 -*-
"""af_shared — 生成器与主流程共享的底层工具（v4.0.0 模块化第四刀）。

叶模块：不依赖 gen_figure/af_draw，被两者共同导入。
"""
import re

_STYLE_NO_GRID = [False]  # v3.3 --style nature-clean：图型级网格关闭开关

# v3.0.0 模块化：wizard 与异常诊断系统拆至独立模块（原名在此命名空间可用）
from af_wizard import _run_wizard
from af_diagnostics import (_EXIT_DATA_CLASSES, _EXIT_ENV_CLASSES,
                            _classify_exit_code, _diagnose_exception,
                            _print_v3_error, _EXC_ZH_V3, _DIAG_PATTERNS,
                            _KNOWN_DATA_FIELDS)

try:
    import af_v23_stats as _afstats
    import af_v23_charts as _afcharts
except ImportError:  # v2.3 新图型/统计模块不在同目录时降级
    _afstats = None
    _afcharts = None

HATCH_PATTERNS = ['//', '\\\\', '||', '--', '++', 'xx', '..', 'oo', '**', 'oo']

def has_cjk(text):
    """Check if text contains CJK characters (incl. supplementary-plane ideographs)."""
    if not text:
        return False
    for ch in str(text):
        o = ord(ch)
        if 0x4e00 <= o <= 0x9fff or 0x3400 <= o <= 0x4dbf:  # BMP: CJK Unified + Ext-A
            return True
        if 0x3000 <= o <= 0x303f or 0xff00 <= o <= 0xffef:  # CJK 标点 + 全角形式（（）：等）
            return True
        if 0x20000 <= o <= 0x2ebef:  # Ext-B..F (rare, but real ideographs)
            return True
        if 0x30000 <= o <= 0x3134f:  # Ext-G
            return True
    return False



def _ensure_ylabel_clear(ax, fig=None, max_pad=24.0):
    """Mechanism-level: auto-increase y-label labelpad until it clears tick labels.

    Rotated (90°) y-axis titles -- especially long CJK+English mixes like
    "最高研发阶段 (max phase)" -- can collide with the top/bottom tick labels
    even when tick-vs-tick overlaps are handled. Measures real rendered
    bounding boxes; only grows the pad when a collision exists, so figures
    that already look right are left untouched.
    """
    fig = fig or ax.figure
    label = ax.yaxis.get_label()
    if not label.get_text().strip():
        return
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    label_bb = label.get_window_extent(renderer)
    tick_bbs = [t.get_window_extent(renderer) for t in ax.get_yticklabels()
                if t.get_text().strip() and t.get_visible()]
    if not tick_bbs:
        return
    cur = ax.yaxis.labelpad

    def collides():
        for tb in tick_bbs:
            inter = BboxBase.intersection(label_bb, tb)
            if inter is not None and inter.width > 0 and inter.height > 0:
                return True
        return False

    while collides() and cur <= max_pad:
        cur += 1.0
        ax.yaxis.labelpad = cur
        fig.canvas.draw()
        label_bb = label.get_window_extent(renderer)
    if collides():
        # Pad exhausted: shrink the label font as a last resort.
        label.set_fontsize(max(5, label.get_fontsize() - 1))
        fig.canvas.draw()
        print(f"WARNING: y-label '{label.get_text()[:20]}...' still near ticks "
              f"after pad={cur:.0f}, font shrunk", file=sys.stderr)

