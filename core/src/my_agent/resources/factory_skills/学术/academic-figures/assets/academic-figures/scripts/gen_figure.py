#!/usr/bin/env python3





















import argparse, json, csv, subprocess, sys, os, time, threading

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.transforms import BboxBase
import numpy as np


from af_wizard import _run_wizard
from af_diagnostics import (_EXIT_DATA_CLASSES, _EXIT_ENV_CLASSES,
                            _classify_exit_code, _diagnose_exception,
                            _print_v3_error, _EXC_ZH_V3, _DIAG_PATTERNS,
                            _KNOWN_DATA_FIELDS)

try:
    import af_v23_stats as _afstats
    import af_v23_charts as _afcharts
except ImportError:  
    _afstats = None
    _afcharts = None


from af_shared import has_cjk, HATCH_PATTERNS, _STYLE_NO_GRID, _ensure_ylabel_clear
from af_draw import (GENERATORS, apply_base_style, _darken_color, _sig_stars,
                     pairwise_vs_first, draw_bootstrap_brackets,
                     annotate_bootstrap_stats, draw_stat_brackets,
                     annotate_auto_stats, annotate_multi_stats,
                     gen_bar, gen_heatmap, gen_scatter, gen_line, gen_box,
                     gen_forest, gen_violin, gen_km, gen_roc, gen_stacked_bar,
                     gen_dual_axis, gen_composite, gen_diagram, gen_prisma)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DETECT_SCRIPT = os.path.join(SCRIPT_DIR, "detect_cjk_font.py")


THEMES = {
    
    
    "classic": {
        "figsize": (10, 6),
        "dpi": 600,
        "font_size": 11,
        "colors": ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860",
                   "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD"],
        "grid_alpha": 0.3,
        "spines": ["top", "right"],  
        "colorblind_safe": False,
    },
    
    
    "okabe-ito": {
        "figsize": (8, 5.5),
        "dpi": 600,
        "font_size": 7,
        "colors": ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2",
                   "#D55E00", "#CC79A7", "#000000", "#999999", "#44AA99"],
        "grid_alpha": 0.2,
        "spines": ["top", "right"],
        "colorblind_safe": True,
    },
    "nature": {
        "figsize": (8, 5.5),
        "dpi": 600,
        "font_size": 7,
        "colors": ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F", "#8491B4",
                   "#91D1C2", "#DC0000", "#7E6148", "#B09C85"],
        "grid_alpha": 0.2,
        "spines": ["top", "right"],
        "colorblind_safe": False,
    },
    "lancet": {
        "figsize": (9, 6),
        "dpi": 600,
        "font_size": 7,
        "colors": ["#00468B", "#ED0000", "#42B540", "#0099B4", "#525252", "#7F6F00",
                   "#ED7D31", "#8B6914", "#4C0099", "#99CC00"],
        "grid_alpha": 0.25,
        "spines": ["top", "right"],
        "colorblind_safe": False,
    },
    
    "nejm": {
        "figsize": (9, 6),
        "dpi": 600,
        "font_size": 8,
        "colors": ["#BC3C29", "#0072B5", "#E18727", "#20854E", "#7876B1", "#6F99AD",
                   "#FFDC91", "#EE4C97"],
        "grid_alpha": 0.25,
        "spines": ["top", "right"],
        "colorblind_safe": False,
    },
    
    "science": {
        "figsize": (8, 5.5),
        "dpi": 600,
        "font_size": 7,
        "colors": ["#3B4992", "#EE0000", "#008B45", "#631879", "#008280", "#BB0021",
                   "#5F559B", "#A20056", "#808180", "#1B1919"],
        "grid_alpha": 0.2,
        "spines": ["top", "right"],
        "colorblind_safe": False,
    },
    "conservative": {
        "figsize": (9, 5.5),
        "dpi": 600,
        "font_size": 8,
        "colors": ["#2E86C1", "#A0A0A0", "#E74C3C", "#27AE60", "#F39C12", "#8E44AD",
                   "#1ABC9C", "#E67E22", "#34495E", "#16A085"],
        "grid_alpha": 0.3,
        "spines": ["top", "right"],
        "colorblind_safe": False,
    },
    
    
    
    
    "glm": {
        "figsize": (10, 6),
        "dpi": 600,
        "font_size": 11,
        "colors": ["#5B8DBE",  
                   "#D79D55",  
                   "#6BA776",  
                   "#9B7BB8",  
                   "#C9694E",  
                   "#5BA0A0",  
                   "#B47A8E",  
                   "#7A7A7A",  
                   "#C4A44A",  
                   "#7AAF42"],  
        "grid_alpha": 0.15,
        "spines": ["top", "right"],
        "colorblind_safe": True,
    },
    "glm-brand": {
        "figsize": (10, 6),
        "dpi": 600,
        "font_size": 11,
        "colors": ["#2E5E8F",  
                   "#FFB627",  
                   "#6BA776",  
                   "#9B7BB8",  
                   "#C9694E",  
                   "#5BA0A0",  
                   "#B47A8E",  
                   "#7A7A7A",  
                   "#C4A44A",  
                   "#8A9BA8"],  
        "spines": ["top", "right"],
        "grid_alpha": 0.0,  
        "hatch_edge": "auto",  
    },
    
    
    
    "cool": {
        "figsize": (9, 5.5),
        "dpi": 600,
        "font_size": 8,
        "colors": ["#1B4965",  
                   "#2E6F9E",  
                   "#4FA3C5",  
                   "#3D8080",  
                   "#62A0A8",  
                   "#5B7BA0",  
                   "#7B9AB5",  
                   "#9DB5CC"],  
        "grid_alpha": 0.15,
        "spines": ["top", "right"],
        "colorblind_safe": True,
    },
}

THEME_ALIASES = {
    "okabe": "okabe-ito", "colorblind": "okabe-ito", "colorblind-safe": "okabe-ito",
    "okabeIto": "okabe-ito", "okabeito": "okabe-ito",
    "classic": "classic", "matplotlib": "classic", "default": "glm",
    "glm": "glm", "glm-blog": "glm", "glmblog": "glm", "glm-brand": "glm-brand", "brand": "glm-brand", "glmb": "glm-brand",
    "cool": "cool", "cool-toned": "cool",
    "nature": "nature", "npg": "nature",
    "lancet": "lancet", "the-lancet": "lancet",
    "nejm": "nejm", "new-england": "nejm", "new-england-journal": "nejm",
    "science": "science", "aaas": "science",
    "conservative": "conservative", "conserv": "conservative",
}

THEME_SWATCH_DESCRIPTIONS = {
    "glm": "GLM 素雅莫兰迪风（默认）· 色盲安全 · 钢蓝/暖黄/鼠尾草绿/灰紫/珊瑚",
    "glm-brand": "GLM 品牌视觉 · 信号黄对比强化 · 无网格 · 同系深色斜纹（Pro 默认）",
    "classic": "经典 matplotlib 色板（v2.0 前的旧默认）",
    "okabe-ito": "Nature Methods 金标准 · 色盲安全 · 橙/天蓝/绿/黄/深蓝/红",
    "nature": "NPG 期刊风 · 红/蓝/绿/藏蓝",
    "lancet": "The Lancet 期刊风 · 深蓝/红/绿",
    "nejm": "NEJM 期刊风 · 砖红/钢蓝/橙/绿（8 色）",
    "science": "Science（AAAS）期刊风 · 藏蓝/红/绿/紫（10 色）",
    "conservative": "保守学术 · 蓝灰为主",
    "cool": "冷色调 · 深海军蓝→浅钢蓝 8 阶 · 色盲安全",
}

THEME_ORDER = ["glm", "classic", "okabe-ito", "nature", "lancet", "nejm", "science",
               "conservative", "cool"]


def resolve_theme(name):


    if not name:
        return "glm"
    key = name.strip().lower()
    if key in THEMES:
        return key
    if key in THEME_ALIASES:
        return THEME_ALIASES[key]
    for canonical in THEMES:
        if canonical.startswith(key):
            return canonical
    return None


CHART_NOTES = {
    "bar": "bar/hbar: JSON 或 CSV 均可；CSV 首列为 X 标签。误差棒需 JSON errors 字段（CSV 不支持）。--hatch 斜纹适合打印/黑白场景。",
    "grouped_bar": "同 bar。多 series 自动分组；--show-ratio 显示比值标注。",
    "hbar": "同 bar（horizontal）。标签过长时 horizontal 模式更合适。",
    "stacked_bar": "stacked_bar: 构成比堆叠；JSON percentage=true 归一化为 100%；CSV 每列为一个 series。",
    "heatmap": "heatmap: JSON matrix 必填（rows/cols 可选）；--cmap 自定义色阶；大矩阵建议 PNG/SVG。",
    "scatter": "scatter: JSON 或 CSV；groups 字段区分颜色；--no-trend 关闭趋势线。",
    "line": "line: JSON series 或多列 CSV；x 轴标签 JSON labels 或 CSV 首列。",
    "dual_axis": "dual_axis: 需要 JSON 含 left/right 两个 series 定义；CSV 不支持双轴。",
    "box": "box: 每列为一个分布；CSV 或 JSON datasets。",
    "forest": "forest: meta 分析森林图；JSON estimates/ci_low/ci_high 必填，可选 weights/overall/heterogeneity/events。",
    "km": "km: Kaplan-Meier；JSON 需 time/status 数据结构，参考文档 §统计数据。",
    "roc": "roc: ROC 曲线；JSON 需 scores/labels，参考文档 §统计数据。",
    "violin": "violin: 小提琴图；JSON datasets 或 CSV，每列为分布。",
    "composite": "composite: 多面板组合图；JSON panels 数组定义子图，参考文档 §组合图。",
    "diagram": "diagram: 架构/流程图；JSON boxes/arrows，CONSORT 式，参考文档 §流程图。",
    "prisma": "prisma: PRISMA 2020 系统综述流程图；JSON 需 records_identified/studies_included，"
              "数字自洽性自动校验（对不上报 ERROR 拒绝出图）；lang=zh 输出中文标准版；"
              "参考文档 §PRISMA 流程图。",
    "funnel": "funnel: Meta 漏斗图；JSON studies（每项 name/effect/se，效应建议 log 尺度）；"
              "自动 DL 随机效应合并线+95% 伪置信漏斗；--egger 加不对称回归线（<5 研究警告）。",
    "bland_altman": "bland_altman: 一致性分析；JSON methods 恰好两项系列或 a/b 数组；"
                    "自动均值差线与 ±1.96SD 一致性界线。",
    "pca": "pca: PCA 得分图；JSON matrix（行=样本 列=特征），可选 groups（分组椭圆±2SD）与 "
           "feature_names（载荷箭头 top5）；默认标准化（相关矩阵），列上限 200。",
    "paired": "paired: 配对前后图；JSON before/after 或 series 恰好两项（等长）；"
              "--stats auto 加配对检验（配对 t / Wilcoxon 符号秩）括号星号。",
    "venn": "venn: 韦恩图（2~4 集合；4 集合为椭圆布局 v2.8）；JSON sets 为元素列表（自动求交并）或全部区域计数；"
            "默认等圆示意、区域数字精确；--area 按计数比例绘制（Euler，2 集合解析解/"
            "3 集合最优拟合）。",
    "cluster_heatmap": "cluster_heatmap: 聚类热图；数据格式同 heatmap（matrix），行列按 Ward 层次"
                       "聚类重排（顺序写入 stderr/alt）；行数上限 3000；v2.3 暂不含树状图面板。",
}


def cmd_list_themes():

    for t in THEME_ORDER:
        desc = THEME_SWATCH_DESCRIPTIONS.get(t, "")
        colors = THEMES[t]["colors"]
        blocks = "".join(f"\x1b[48;2;{int(c[1:3],16)};{int(c[3:5],16)};{int(c[5:7],16)}m  \x1b[0m"
                         for c in colors)
        safe = "色盲安全" if THEMES[t].get("colorblind_safe") else ""
        print(f"  {t:<14} {blocks}  {desc} {safe}")
    print("\n用法: --theme <name>   别名: okabe→okabe-ito, colorblind→okabe-ito, classic/default→glm")


def cmd_theme_swatch(theme_key, out):

    t = THEMES[theme_key]
    colors = t["colors"]
    n = len(colors)
    import matplotlib.patches as mpatches
    fig, ax = plt.subplots(figsize=(max(6, n * 0.75), 2.2))
    ax.set_xlim(0, n)
    ax.set_ylim(0, 1)
    ax.axis("off")
    for i, c in enumerate(colors):
        rect = mpatches.Rectangle((i + 0.1, 0.15), 0.8, 0.55, facecolor=c,
                                  edgecolor='black', linewidth=0.5)
        ax.add_patch(rect)
        ax.text(i + 0.5, 0.85, c, ha='center', va='bottom', fontsize=8)
    fig.suptitle(f"Theme: {theme_key}  ({n} colors)"
                 + ("  ·  colorblind-safe" if t.get("colorblind_safe") else ""),
                 fontsize=11, fontweight='bold')
    fig.savefig(out, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"Swatch saved: {out}", file=sys.stderr)


DEMO_DATA = {
    "bar": {"labels": ["TNF抑制剂", "IL-6抑制剂", "JAK抑制剂", "IL-1抑制剂", "CTLA-4融合"],
            "series": {"应答率(%)": [62, 55, 48, 40, 35], "缓解率(%)": [28, 22, 20, 15, 10]}},
    "hbar": {"labels": ["TNF抑制剂", "IL-6抑制剂", "JAK抑制剂", "IL-1抑制剂", "CTLA-4融合"],
             "series": {"ACR50应答率(%)": [62, 55, 48, 40, 35]}},
    "stacked_bar": {"labels": ["队列A", "队列B", "队列C"],
                    "series": {"缓解": [45, 38, 30], "部分缓解": [25, 30, 28], "无缓解": [30, 32, 42]},
                    "percentage": True},
    "heatmap": {"rows": ["IL-6", "TNF-α", "CRP", "ESR"],
                "cols": ["IL-6", "TNF-α", "CRP", "ESR"],
                "matrix": [[1.0, 0.72, 0.85, 0.68], [0.72, 1.0, 0.65, 0.60],
                           [0.85, 0.65, 1.0, 0.75], [0.68, 0.60, 0.75, 1.0]]},
    "line": {"labels": ["0周", "4周", "8周", "12周", "16周"],
             "series": {"TNF抑制剂": [5.8, 4.2, 3.5, 3.0, 2.6], "联合治疗": [5.9, 3.8, 2.8, 2.2, 1.8]}},
    "scatter": {"x": [2, 4, 8, 12, 16, 20, 24, 28],
                "y": [45, 38, 28, 22, 18, 15, 12, 10],
                "groups": ["应答者", "应答者", "应答者", "应答者",
                           "非应答者", "非应答者", "非应答者", "非应答者"]},
    "forest": {"labels": ["Smith 2023", "Tanaka 2023", "Brown 2022", "王明 2024"],
               "estimates": [0.72, 0.80, 0.75, 0.65],
               "ci_low": [0.55, 0.62, 0.56, 0.48],
               "ci_high": [0.94, 1.03, 1.00, 0.84],
               "overall": {"estimate": 0.73, "ci_low": 0.60, "ci_high": 0.88}},
    "km": {"groups": {"治疗组": [[0, 1.0], [6, 0.8], [12, 0.7], [18, 0.6], [24, 0.55]],
                      "对照组": [[0, 1.0], [6, 0.9], [12, 0.75], [18, 0.6], [24, 0.45]]},
           "log_rank": {"p": 0.03}},
    "roc": {"curves": [{"fpr": [0.0, 0.1, 0.2, 0.4, 0.6, 1.0],
                        "tpr": [0.0, 0.6, 0.8, 0.9, 0.95, 1.0],
                        "label": "模型A", "auc": 0.92},
                       {"fpr": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
                        "tpr": [0.0, 0.4, 0.6, 0.75, 0.85, 1.0],
                        "label": "模型B", "auc": 0.85}]},
    "violin": {"datasets": {"组A": [1.2, 2.3, 2.1, 3.0, 2.8, 3.5], "组B": [2.0, 2.4, 3.1, 3.8, 4.2, 4.0],
                            "组C": [3.0, 3.2, 3.8, 4.5, 4.8, 5.2]}},
    "box": {"datasets": {"组A": [1.2, 2.3, 2.1, 3.0, 2.8, 3.5], "组B": [2.0, 2.4, 3.1, 3.8, 4.2, 4.0]}},
    "slope": {"left_label": "基线", "right_label": "12 周",
              "items": {"药物A": [72, 85], "药物B": [65, 61], "对照": [70, 71]}},
    "volcano": {"log2fc": [-2.3, -1.4, -1.1, -0.4, 0.2, 0.6, 1.2, 1.6, 2.4],
                "pvalue": [3e-4, 0.012, 0.04, 0.5, 0.8, 0.3, 0.02, 3e-5, 8e-7],
                "names": ["SLC6A4", "MAOA", "FKBP5", "NR3C1", "CRH", "AVP",
                          "BDNF", "COMT", "HTR1A"]},
    "dual_axis": {"labels": ["0周", "4周", "8周", "12周"],
                  "left": {"DAS28": [5.8, 4.2, 3.5, 3.0]},
                  "right": {"CRP(mg/L)": [42, 30, 22, 16]}},
    "prisma": {"records_identified": 128, "duplicates_removed": 23, "records_excluded": 61,
               "reports_not_retrieved": 3,
               "exclusion_reasons": {"人群不符": 5, "干预不符": 7, "数据不可用": 4},
               "studies_included": 25},
}


def cmd_demo(args):

    print("Academic Figures 交互演示 (v2.0+)\n选择图表类型:")
    types = [k for k in DEMO_DATA.keys() if k in GENERATORS]
    for i, t in enumerate(types, 1):
        print(f"  [{i}] {t}")
    sel = input(f"输入序号 (1-{len(types)}, 回车=1): ").strip() or "1"
    try:
        chart_type = types[int(sel) - 1]
    except (ValueError, IndexError):
        print("无效输入，使用 bar", file=sys.stderr)
        chart_type = "bar"
    import tempfile, json as _json
    tmpdir = tempfile.mkdtemp(prefix="af_demo_")
    data_path = os.path.join(tmpdir, "data.json")
    out_path = os.path.join(tmpdir, f"{chart_type}.png")
    with open(data_path, "w", encoding="utf-8") as f:
        _json.dump(DEMO_DATA[chart_type], f, ensure_ascii=False)
    cmd = (f"python3 scripts/gen_figure.py -t {chart_type} -d '{data_path}' -o '{out_path}' "
           f"--theme {args.theme or 'glm'}")
    print(f"\n执行: {cmd}", file=sys.stderr)
    args.type, args.data, args.out = chart_type, data_path, out_path
    return True


def cmd_explain(chart_type):

    if chart_type not in GENERATORS:
        print(f"未知图表类型: {chart_type}", file=sys.stderr)
        print(f"可用: {', '.join(GENERATORS.keys())}", file=sys.stderr)
        sys.exit(1)
    print(f"[{chart_type}]")
    print(CHART_NOTES.get(chart_type, "参考文档相应章节。"))




def suggest_chart_type(data):





    if not isinstance(data, dict):
        return []
    recs = []
    keys = set(data.keys())
    if "records_identified" in keys or "studies_included" in keys:
        recs.append((98, "prisma", "PRISMA flow fields (records_identified / studies_included)"))
    if "blocks" in keys and "arrows" in keys:
        recs.append((96, "diagram", "blocks + arrows structure"))
    if "panels" in keys:
        recs.append((92, "composite", "multi-panel 'panels' definition"))
    curves = data.get("curves")
    if isinstance(curves, list) and curves and isinstance(curves[0], dict) \
            and {"fpr", "tpr"} <= set(curves[0]):
        recs.append((95, "roc", "curves[] with fpr/tpr arrays"))
    groups = data.get("groups")
    if isinstance(groups, dict) and groups:
        first = next(iter(groups.values()), None)
        if isinstance(first, list) and first and isinstance(first[0], (list, tuple)) \
                and len(first[0]) == 2:
            recs.append((94, "km", "groups mapped to [time, survival] step pairs"))
    if {"estimates", "ci_low", "ci_high"} <= keys:
        recs.append((93, "forest", "effect estimates with CI bounds"))
    if isinstance(data.get("matrix"), list):
        recs.append((88, "heatmap", "2D 'matrix'"))
    if {"left", "right"} <= keys:
        recs.append((86, "dual_axis", "left + right series for dual Y-axis"))
    if isinstance(data.get("datasets"), dict) and data["datasets"]:
        recs.append((72, "violin", "raw per-group 'datasets' — distribution view"))
        recs.append((70, "box", "raw per-group 'datasets' — boxplot view"))
    x, y = data.get("x"), data.get("y")
    if isinstance(x, list) and isinstance(y, list) and x and len(x) == len(y):
        recs.append((80, "scatter", "paired x/y arrays"))
    series = data.get("series")
    if isinstance(series, dict) and series:
        lists = [v for v in series.values() if isinstance(v, list)]
        if lists and all(len(v) == 1 for v in lists):
            recs.append((68, "bar", "single-value series"))
        else:
            recs.append((76, "bar", "labels + named series"))
    return sorted(recs, key=lambda r: (-r[0], r[1]))


def cmd_suggest(data_path):

    try:
        data = load_data(data_path)
    except Exception as e:
        print(f"ERROR: cannot load '{data_path}': {e}", file=sys.stderr)
        sys.exit(1)
    recs = suggest_chart_type(data)
    if not recs:
        print("No confident match — default to bar (labels + series). See --explain <type>.")
        return
    print("Suggested chart types (best first):")
    for i, (score, ctype, why) in enumerate(recs[:3], 1):
        print(f"  [{i}] {ctype:<12} score {score:<3} — {why}")
    best = recs[0][1]
    print(f"\nRun: python3 scripts/gen_figure.py -t {best} -d '{data_path}' -o out.pdf "
          f"--theme okabe-ito --verify")



JOURNAL_PRESETS = {
    "nature": {"widths_mm": {"single": 89, "double": 183},
               "font_size": 7, "min_text_size": 5, "font_family": "Helvetica", "dpi": 600},
    "lancet": {"widths_mm": {"single": 85, "double": 183},
               "font_size": 8, "min_text_size": 6, "font_family": "Arial", "dpi": 600},
    
    
    
    "science": {"widths_mm": {"single": 55, "double": 120},
                "font_size": 7, "min_text_size": 5, "font_family": "Helvetica", "dpi": 600},
    "cell": {"widths_mm": {"single": 85, "double": 176},
             "font_size": 8, "min_text_size": 6, "font_family": "Arial", "dpi": 300},
    "nejm": {"widths_mm": {"single": 89, "double": 190},
             "font_size": 8, "min_text_size": 6, "font_family": "Helvetica", "dpi": 300},
    "jama": {"widths_mm": {"single": 89, "double": 183},
             "font_size": 8, "min_text_size": 6, "font_family": "Arial", "dpi": 600},
    "ieee": {"widths_mm": {"single": 89, "double": 181},
             "font_size": 8, "min_text_size": 6, "font_family": "Times New Roman", "dpi": 600},
    
    "cma": {"widths_mm": {"single": 80, "double": 170},
            "font_size": 8, "min_text_size": 6, "font_family": "Arial", "dpi": 600,
            "cjk_default": True},
    "cn-core": {"widths_mm": {"single": 80, "double": 170},
                "font_size": 9, "min_text_size": 6, "font_family": "Arial", "dpi": 300,
                "cjk_default": True},
}

def _memory_hint(data, chart_type):

    try:
        n = 0
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    n += len(v)
                    n += sum(len(x) for x in v if isinstance(x, (list, tuple)))
                elif isinstance(v, dict):
                    for vv in v.values():
                        n += len(vv) if isinstance(vv, list) else 1
                elif isinstance(v, (int, float)):
                    n += 1
            if isinstance(data.get("matrix"), list):
                n = sum(len(r) for r in data["matrix"] if isinstance(r, list))
        if n > 1_000_000:
            print(f"提示：数据规模约 {n} 个数值点，内存占用较大。热图/聚类建议先按行聚合；"
                  "散点建议等距抽样到 1 万点内；也可降低 --dpi。", file=sys.stderr)
    except Exception:
        pass


def _load_journal_presets(base_dir=None):


    import glob as _glob
    d = os.path.join(base_dir or os.path.dirname(os.path.abspath(__file__)), "journal")
    out = {}
    if os.path.isdir(d):
        for p in sorted(_glob.glob(os.path.join(d, "*.json"))):
            name = os.path.splitext(os.path.basename(p))[0]
            try:
                with open(p, encoding="utf-8") as fh:
                    spec = json.load(fh)
                for k in ("widths_mm", "font_size", "dpi"):
                    if k not in spec:
                        raise KeyError(f"缺少 {k}")
                out[name] = spec
            except Exception as exc:
                print(f"WARNING: 期刊预设 {os.path.basename(p)} 加载失败（{exc}），回退内置值",
                      file=sys.stderr)
    for k, v in _JOURNAL_BUILTIN.items():
        out.setdefault(k, v)
    return out


_JOURNAL_BUILTIN = {k: dict(v) for k, v in JOURNAL_PRESETS.items()}
JOURNAL_PRESETS = _load_journal_presets()


JOURNAL_THEME = {"nature": "nature", "lancet": "lancet",
                 "nejm": "nejm", "science": "science"}





def _alt_num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def generate_alt_text(chart_type, data, title=""):


    if _afcharts is not None and chart_type in _afcharts.EXTRA_GENERATORS:
        return _afcharts.alt_extra(chart_type, data, title)
    t = f"{title}。" if title else ""

    def _max_txt(vals):
        fv = [_alt_num(v) for v in vals if isinstance(vals, list)]
        fv = [v for v in fv if v is not None]
        return f"{max(fv):g}" if fv else "?"

    if chart_type in ("bar", "grouped_bar", "hbar", "horizontal_bar"):
        series = data.get("series", {})
        labels = data.get("labels", [])
        parts = []
        for name, vals in series.items():
            fv = [v for v in (_alt_num(x) for x in vals) if v is not None]
            if fv:
                parts.append(f"{name} 最大值 {max(fv):g}")
        return (f"柱状图。{t}共 {len(labels)} 组：{'、'.join(map(str, labels))}。"
                f"{'；'.join(parts)}。")
    if chart_type in ("box", "boxplot", "violin"):
        series = data.get("series", {})
        segs = []
        for name, vals in series.items():
            fv = sorted(v for v in (_alt_num(x) for x in vals) if v is not None)
            if fv:
                segs.append(f"{name}：中位数 {fv[len(fv)//2]:g}（n={len(fv)}）")
        kind = "箱线图" if chart_type in ("box", "boxplot") else "小提琴图"
        return f"{kind}。{t}{'；'.join(segs)}。"
    if chart_type in ("km", "survival"):
        groups = data.get("groups", {})
        lr = data.get("log_rank") or {}
        tail = f"Log-rank p = {lr.get('p')}。" if lr.get("p") is not None else ""
        return (f"Kaplan-Meier 生存曲线。{t}分组：{'、'.join(groups.keys())}。{tail}")
    if chart_type == "roc":
        curves = data.get("curves", [])
        names = "；".join(f"{c.get('name', 'curve')} AUC {c.get('auc', '?')}"
                          for c in curves)
        return f"ROC 曲线。{t}{names}。"
    if chart_type == "forest":
        o = data.get("overall") or {}
        o_txt = (f"合并效应 {o.get('estimate')}（95%CI {o.get('ci_low')}–{o.get('ci_high')}）。"
                 if o else "")
        return f"森林图，{len(data.get('labels', []))} 项研究。{t}{o_txt}"
    if chart_type == "heatmap":
        m = data.get("matrix", [])
        cols = len(m[0]) if m else 0
        return f"热图，{len(m)} 行 × {cols} 列。{t}"
    if chart_type == "prisma":
        return (f"PRISMA 2020 系统综述流程图：最初识别 "
                f"{data.get('records_identified')} 条记录，最终纳入 "
                f"{data.get('studies_included')} 项研究。{t}")
    if chart_type == "composite":
        panels = data.get("panels", [])
        names = "、".join(str(p.get("title", "")) for p in panels)
        return f"多面板组合图，{len(panels)} 个面板：{names}。{t}"
    if chart_type == "line":
        series = data.get("series", {})
        n_pts = len(next(iter(series.values()), []))
        return f"折线图，{len(series)} 条系列 × {n_pts} 个数据点。{t}"
    if chart_type == "scatter":
        return f"散点图，共 {len(data.get('x', []))} 个数据点。{t}"
    if chart_type == "dual_axis":
        return f"双 Y 轴折线图。{t}"
    if chart_type == "diagram":
        return f"流程图。{t}"
    return f"{chart_type} 图。{t}"



def load_cjk_font(font_path=None):

    if font_path is None:
        
        import subprocess
        try:
            result = subprocess.run(
                [sys.executable, DETECT_SCRIPT],
                capture_output=True, text=True, timeout=10
            )
            info = json.loads(result.stdout)
            font_path = info.get("path") if info.get("found") else None
        except Exception:
            font_path = None
    if font_path and os.path.exists(font_path):
        fm.fontManager.addfont(font_path)
        fp = fm.FontProperties(fname=font_path)
        
        return fp, fp.get_name()
    return None, None



def safe_text(ax, text, fontprop=None, **kwargs):

    if fontprop and has_cjk(str(text)):
        return ax.set_text(text) if hasattr(ax, 'set_text') else ax.text(text, fontproperties=fontprop, **kwargs)
    return ax.set_text(text) if hasattr(ax, 'set_text') else ax.text(text, **kwargs)




MIN_TICK_GAP = 6.0


def _boxes_overlap(b1, b2, ratio=0.04):

    inter = BboxBase.intersection(b1, b2)
    if inter is None or inter.width <= 0 or inter.height <= 0:
        return False
    inter_area = inter.width * inter.height
    return inter_area > ratio * min(b1.width * b1.height, b2.width * b2.height, 1)


def _adjacent_too_close(b1, b2, axis, min_gap=MIN_TICK_GAP):







    inter = BboxBase.intersection(b1, b2)
    if inter is not None and inter.width > 0 and inter.height > 0:
        return True
    if axis == 'x':
        gap = b2.x0 - b1.x1 if b2.x0 >= b1.x0 else b1.x0 - b2.x1
    else:
        gap = b1.y0 - b2.y1 if b1.y0 >= b2.y0 else b2.y0 - b1.y1
    return gap < min_gap


def _tick_boxes(ax, renderer):

    xl, yl, xb, yb = [], [], [], []
    for lab in ax.get_xticklabels():
        if lab.get_text().strip() and lab.get_visible():
            xl.append(lab)
            xb.append(lab.get_window_extent(renderer))
    for lab in ax.get_yticklabels():
        if lab.get_text().strip() and lab.get_visible():
            yl.append(lab)
            yb.append(lab.get_window_extent(renderer))
    return xl, yl, xb, yb



def _axis_has_overlap(xb, yb):

    for i in range(len(xb) - 1):
        if _boxes_overlap(xb[i], xb[i + 1]) or _adjacent_too_close(xb[i], xb[i + 1], 'x'):
            return True
    for i in range(len(yb) - 1):
        if _boxes_overlap(yb[i], yb[i + 1]) or _adjacent_too_close(yb[i], yb[i + 1], 'y'):
            return True
    for bx in xb:
        for by in yb:
            if _boxes_overlap(bx, by):
                return True
    return False


def _degrade_axis(ax, axis, level):







    labels = ax.get_xticklabels() if axis == 'x' else ax.get_yticklabels()
    labels = [l for l in labels if l.get_text().strip()]
    if not labels:
        return False
    if level == 1 and axis == 'x':
        if all(l.get_rotation() == 45 for l in labels):
            return False
        for l in labels:
            l.set_rotation(45)
            l.set_ha('right')
        return True
    if level == 2 and axis == 'x':
        wrapped = False
        for l in labels:
            if ' ' in l.get_text() and '\n' not in l.get_text():
                l.set_text('\n'.join(l.get_text().split(' ')))
                wrapped = True
        return wrapped
    if level == 3:
        sizes = {l.get_fontsize() for l in labels}
        if all(s <= 5 for s in sizes):
            return False
        for l in labels:
            l.set_fontsize(max(5, l.get_fontsize() - 1))
        return True
    if level == 4 and axis == 'x':
        if all(l.get_rotation() == 90 for l in labels):
            return False
        for l in labels:
            l.set_rotation(90)
            l.set_ha('center')
        return True
    if level >= 5:
        stride = 2 ** (level - 4)
        hid = False
        for i, l in enumerate(labels):
            if i % stride != 0 and l.get_visible():
                l.set_visible(False)
                hid = True
        return hid
    return False


def fix_tick_overlaps(fig):








    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for _pass in range(8):
        fixed_any = False
        for ax in fig.axes:
            if getattr(ax, "_af_category_axis", False):
                continue  
            xl, yl, xb, yb = _tick_boxes(ax, renderer)
            if not _axis_has_overlap(xb, yb):
                continue
            for level in range(1, 11):
                if not _axis_has_overlap(xb, yb):
                    break
                if level in (1, 2, 4) and not xl:
                    continue
                applied = _degrade_axis(ax, 'x', level)
                if not applied and level >= 3:
                    applied = _degrade_axis(ax, 'y', level)
                if applied:
                    fixed_any = True
                    fig.canvas.draw()
                    renderer = fig.canvas.get_renderer()
                    xl, yl, xb, yb = _tick_boxes(ax, renderer)
        if not fixed_any:
            break

    hidden = sum(1 for ax in fig.axes
                 for l in ax.get_xticklabels() + ax.get_yticklabels()
                 if l.get_text().strip() and not l.get_visible())
    if hidden:
        print(f"academic-figures WARNING: hid {hidden} tick label(s) to resolve "
              f"overlap — hidden labels are lost data; increase --width/--height "
              f"or shorten labels", file=sys.stderr)


def place_annotation(ax, text, xy, fontsize=9.5, fontweight='bold', color='black', ha='center'):


    fig = ax.figure
    candidates = [(0, 14), (0, -24), (16, 0), (-16, 0), (0, 32), (0, -42),
                  (30, 14), (-30, 14), (30, -24), (-30, -24), (30, 32), (-30, -42)]
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    placed = [t.get_window_extent(renderer) for t in ax.texts if t.get_text().strip()]
    for dx, dy in candidates:
        t = ax.annotate(text, xy=xy, xytext=(dx, dy), textcoords='offset points',
                        ha=ha, va='center', fontsize=fontsize, fontweight=fontweight, color=color)
        fig.canvas.draw()
        bb = t.get_window_extent(renderer)
        if not any(_boxes_overlap(bb, pb) for pb in placed):
            return t
        t.remove()
    return ax.annotate(text, xy=xy, xytext=(0, 14), textcoords='offset points',
                       ha=ha, va='center', fontsize=fontsize, fontweight=fontweight, color=color)




def _is_number(s):

    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _read_excel(path, sheet=None):


    try:
        import openpyxl
    except ImportError:
        raise ValueError(
            "xlsx requires openpyxl — install with: pip install openpyxl "
            "(or export the sheet to CSV)")
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as e:
        raise ValueError(
            f"cannot read {os.path.basename(path)} as Excel (.xlsx): {e} — "
            f"if the file is CSV/TSV, rename it to .csv")
    try:
        if sheet and sheet not in wb.sheetnames:
            raise ValueError(f"sheet '{sheet}' not found in {os.path.basename(path)} — "
                             f"available: {wb.sheetnames}")
        ws = wb[sheet] if sheet else wb.active
        rows_raw = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    rows_raw = [r for r in rows_raw
                if any(v is not None and str(v).strip() != "" for v in r)]
    if not rows_raw:
        raise ValueError(f"sheet is empty: {os.path.basename(path)}")
    headers = ["" if v is None else str(v).strip() for v in rows_raw[0]]
    rows = [[("" if v is None else str(v).strip()) for v in r]
            for r in rows_raw[1:]]
    return headers, rows


def load_data(path, chart_type=None, sheet=None):







    ext = os.path.splitext(path)[1].lower()
    if ext == '.json':
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    elif ext in ('.csv', '.tsv', '.xlsx', '.xls'):
        if ext in ('.csv', '.tsv'):
            delimiter = '\t' if ext == '.tsv' else ','
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=delimiter)
                headers = next(reader)
                rows = list(reader)
        else:
            headers, rows = _read_excel(path, sheet)
        
        
        numeric_col_indices = []
        for i, h in enumerate(headers):
            if i == 0:
                continue
            num_count = sum(1 for r in rows if i < len(r) and _is_number(r[i]))
            if num_count > len(rows) * 0.5:
                numeric_col_indices.append(i)

        
        bad_rows = set()
        for i in numeric_col_indices:
            for ri, r in enumerate(rows):
                if ri < len(r) and not _is_number(r[i]):
                    bad_rows.add(ri)

        
        good_rows = [ri for ri in range(len(rows)) if ri not in bad_rows]
        series = {}
        for i in numeric_col_indices:
            vals = [float(rows[ri][i]) for ri in good_rows if ri < len(rows)]
            if vals:
                series[headers[i]] = vals

        
        labels = [rows[ri][0] for ri in good_rows if ri < len(rows)]
        result = {"labels": labels, "series": series}

        
        if chart_type == 'scatter' and series:
            
            all_numeric = []
            for i, h in enumerate(headers):
                num_count = sum(1 for ri in good_rows if ri < len(rows) and _is_number(rows[ri][i]))
                if num_count > len(good_rows) * 0.5:
                    all_numeric.append((i, h))

            if len(all_numeric) >= 2:
                col_i, col_x_name = all_numeric[0]
                col_j, col_y_name = all_numeric[1]
                x_vals = [float(rows[ri][col_i]) for ri in good_rows if ri < len(rows) and col_i < len(rows[ri])]
                y_vals = [float(rows[ri][col_j]) for ri in good_rows if ri < len(rows) and col_j < len(rows[ri])]

                groups = None
                
                if len(all_numeric) >= 3:
                    
                    pass  
                
                _group_hints = {'group', 'groups', 'category', 'categories', 'class', 'label', 'labels', 'type'}
                candidates = []
                for i, h in enumerate(headers):
                    if i in [idx for idx, _ in all_numeric]:
                        continue
                    vals = [rows[ri][i] for ri in good_rows if ri < len(rows)]
                    unique = set(vals)
                    if len(unique) > 1 and len(unique) <= 20:
                        score = (0, len(unique), i)  
                        if h.lower().strip() in _group_hints:
                            score = (-1, len(unique), i)
                        candidates.append((score, vals, h))
                if candidates:
                    candidates.sort()
                    groups = candidates[0][1]

                result = {"x": x_vals, "y": y_vals}
                if groups:
                    result["groups"] = groups
            elif len(all_numeric) == 1:
                
                col_i, col_name = all_numeric[0]
                y_vals = [float(rows[ri][col_i]) for ri in good_rows if ri < len(rows) and col_i < len(rows[ri])]
                
                if labels and all(_is_number(l) for l in labels):
                    result = {"x": [float(l) for l in labels], "y": y_vals}
                else:
                    result = {"x": list(range(len(y_vals))), "y": y_vals, "groups": labels}

        
        if chart_type in ('box', 'boxplot', 'violin') and series:
            first_col_vals = [rows[ri][0] for ri in good_rows if ri < len(rows)]
            unique_groups = list(dict.fromkeys(first_col_vals))  
            
            if len(unique_groups) < len(first_col_vals) * 0.8 and len(unique_groups) >= 2:
                
                num_col_idx = numeric_col_indices[0] if numeric_col_indices else None
                if num_col_idx is not None:
                    grouped = {}
                    for g in unique_groups:
                        grouped[g] = []
                    for ri in good_rows:
                        if ri < len(rows) and num_col_idx < len(rows[ri]):
                            g = rows[ri][0]
                            v = rows[ri][num_col_idx]
                            if _is_number(v):
                                grouped[g].append(float(v))
                    
                    if any(len(v) >= 2 for v in grouped.values()):
                        result = {"labels": unique_groups, "series": grouped}

        return result
    else:
        raise ValueError(f"不支持的数据格式: {ext}。请改用 .json / .csv / .tsv / .xlsx")




def _preflight_advisories(data, chart_type, downsample=None):

    msgs = []
    try:
        if (chart_type == "cluster_heatmap" and isinstance(data, dict)
                and not downsample):
            rows = len(data.get("matrix") or [])
            if rows > 1500:
                msgs.append(
                    f"cluster_heatmap 行数 {rows} 已超过建议值 1500（硬上限 3000）："
                    "聚类更慢、内存更高——建议加 --downsample 2000 等距采样；"
                    "如确需全量渲染可忽略本提示")
    except Exception:
        pass
    return msgs


def _field_nearmiss_warnings(data):

    msgs = []
    try:
        if isinstance(data, dict):
            import difflib as _dif
            for k in data.keys():
                if (not isinstance(k, str) or k.startswith("_")
                        or k in _KNOWN_DATA_FIELDS):
                    continue
                near = _dif.get_close_matches(k, _KNOWN_DATA_FIELDS, n=1, cutoff=0.6)
                if near:
                    msgs.append(
                        f"字段名 '{k}' 不是有效字段——是否想用 '{near[0]}'？"
                        "（大小写与下划线必须完全一致；无法识别的字段会被忽略；"
                        "各图型字段见 --explain）")
    except Exception:
        pass
    return msgs



_ORDER_CHARTS = ("bar", "grouped_bar", "hbar", "horizontal_bar", "stacked_bar",
                 "box", "violin", "line")
_NORM_CHARTS = ("bar", "grouped_bar", "hbar", "horizontal_bar", "stacked_bar", "line")


def apply_series_order(data, order, chart_type):




    if chart_type in ("box", "violin"):
        series = data.get("series", data.get("datasets"))
        if not isinstance(series, dict) or not series:
            print("WARNING: --order 需要 {组名: 数值数组} 系列型数据，未找到——跳过",
                  file=sys.stderr)
            return
        names = list(series.keys())
        if order == "auto":
            new_names = sorted(
                names,
                key=lambda n: -float(np.median([float(v) for v in series[n]])))
        else:
            want = [w.strip() for w in order.split(",") if w.strip()]
            missing = [w for w in want if w not in names]
            if missing:
                raise ValueError(f"--order 标签未找到：{'、'.join(missing)}"
                                 f"（现有组：{'、'.join(names)}）")
            if sorted(want) != sorted(names):
                raise ValueError("--order 须恰好列出全部组名（不得多/少/重复）")
            new_names = want
        data["series"] = {n: series[n] for n in new_names}
        for k in ("labels", "x"):
            if isinstance(data.get(k), list) and len(data[k]) == len(names):
                data[k] = list(new_names)
        print(f"order: 类别顺序已重排 → {' → '.join(new_names)}", file=sys.stderr)
        return
    labels = data.get("labels", data.get("x"))
    series = data.get("series", data.get("datasets"))
    if not isinstance(labels, list) or not labels or not isinstance(series, dict):
        print("WARNING: --order 需要 labels+series 数据结构，未找到——跳过", file=sys.stderr)
        return
    labels = [str(l) for l in labels]
    if order == "auto":
        first = next(iter(series.values()))
        try:
            fv = [float(first[i]) for i in range(len(labels))]
        except Exception:
            print("WARNING: --order auto 无法读取第一系列数值——跳过", file=sys.stderr)
            return
        pairs = sorted(range(len(labels)), key=lambda i: -fv[i])
        new_labels = [labels[i] for i in pairs]
    else:
        want = [w.strip() for w in order.split(",") if w.strip()]
        missing = [w for w in want if w not in labels]
        if missing:
            raise ValueError(f"--order 标签未找到：{'、'.join(missing)}"
                             f"（现有：{'、'.join(labels)}）")
        if len(want) != len(labels) or len(set(want)) != len(labels):
            raise ValueError("--order 须恰好列出全部类别标签（不得重复/缺漏）")
        new_labels = want
    perm = [labels.index(l) for l in new_labels]

    def _perm(arr):
        if isinstance(arr, list) and len(arr) == len(labels):
            return [arr[i] for i in perm]
        return arr

    data["labels"] = new_labels
    if isinstance(data.get("x"), list):
        data["x"] = new_labels
    for sk, sv in series.items():
        if isinstance(sv, list):
            series[sk] = _perm(sv)
    if isinstance(data.get("errors"), dict):
        for ek, ev in data["errors"].items():
            if isinstance(ev, list):
                data["errors"][ek] = _perm(ev)
    sig = data.get("significance")
    if isinstance(sig, dict) and sig:
        inv = {old: new for new, old in enumerate(perm)}
        data["significance"] = {
            (f"{k.rpartition(':')[0]}:{inv[int(k.rpartition(':')[2])]}"
             if k.rpartition(":")[1] and k.rpartition(":")[2].isdigit()
             and int(k.rpartition(":")[2]) in inv else k): v
            for k, v in sig.items()}
    print(f"order: 类别顺序已重排 → {' → '.join(new_labels)}", file=sys.stderr)


def apply_normalize(data, mode, chart_type):



    series = data.get("series", data.get("datasets"))
    if not isinstance(series, dict) or not series:
        print("WARNING: --normalize 需要 series 数据，未找到——跳过", file=sys.stderr)
        return

    def _num(arr):
        try:
            return [float(v) for v in arr]
        except (TypeError, ValueError):
            return None

    names = list(series.keys())
    conv = {}
    if mode == "baseline":
        base_vals = _num(series[names[0]])
        if not base_vals:
            raise ValueError(f"--normalize baseline：第一系列「{names[0]}」非数值")
        base = float(np.mean(base_vals))
        if base == 0:
            raise ValueError("--normalize baseline：第一系列均值为 0，不能作基线（请检查数据）")
        for n in names:
            vals = _num(series[n])
            if vals is None:
                raise ValueError(f"--normalize：系列「{n}」含非数值")
            series[n] = [v / base for v in vals]
            conv[n] = 1.0 / base
        print(f"normalize baseline: 各系列已÷第一系列「{names[0]}」均值 {base:.4g}"
              f"（该系列现=1.00；误差棒同步缩放；原始数值请保留源数据）", file=sys.stderr)
    else:
        for n in names:
            vals = _num(series[n])
            if not vals:
                raise ValueError(f"--normalize：系列「{n}」非数值")
            if vals[0] == 0:
                raise ValueError(f"--normalize pct100：系列「{n}」首点为 0，"
                                 "不能作基期（请检查数据或改用 --normalize baseline）")
            f = 100.0 / vals[0]
            series[n] = [v * f for v in vals]
            conv[n] = f
        print("normalize pct100: 各系列已按自身首点=100 归一"
              "（误差棒同步缩放；原始数值请保留源数据）", file=sys.stderr)
    if isinstance(data.get("errors"), dict):
        for ek, ev in data["errors"].items():
            vals = _num(ev) if isinstance(ev, list) else None
            if vals and ek in conv:
                data["errors"][ek] = [v * conv[ek] for v in vals]


def _auto_summary(data, chart_type):

    def _num_list(v):
        return [float(x) for x in v if isinstance(x, (int, float))]

    if chart_type in ("km", "survival"):
        groups = data.get("groups") or {}
        if not isinstance(groups, dict) or not groups:
            return None
        n = ev = 0
        for pairs in groups.values():
            for p in pairs if isinstance(pairs, list) else []:
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    n += 1
                    if p[1] == 1:
                        ev += 1
        return f"n={n} 例 · 事件 {ev} 例 · {len(groups)} 组"
    series = data.get("series", data.get("datasets"))
    labels = data.get("labels", data.get("x", []))
    if not isinstance(series, dict) or not series:
        return None
    n = sum(len(_num_list(v)) for v in series.values())
    if n == 0:
        return None
    g_txt = f"{len(labels)} 组" if isinstance(labels, list) and labels else f"{len(series)} 系列"
    return f"n={n} · {g_txt}"


def _doctor_report(args, data):


    import importlib
    issues = 0
    print("── doctor 参数/环境体检（v3.9）──", file=sys.stderr)
    combos = [
        (args.stats in ("auto", "multi", "bootstrap") and args.type not in ("box", "violin"),
         f"--stats {args.stats} 仅 box/violin 生效"),
        (args.stats == "cox" and args.type != "forest", "--stats cox 仅 forest 生效"),
        (bool(args.compare) and args.type != "roc", "--compare 仅 roc 生效"),
        (bool(args.egger) and args.type != "funnel", "--egger 仅 funnel 生效"),
        (bool(args.hatch) and args.type not in ("bar", "grouped_bar", "hbar",
                                                "horizontal_bar", "stacked_bar"),
         "--hatch 仅 bar 系生效"),
        (bool(args.area) and args.type != "venn", "--area 仅 venn 生效"),
        (bool(args.sheet) and not str(args.data or "").lower().endswith((".xlsx", ".xls")),
         "--sheet 仅 .xlsx/.xls 生效"),
        (bool(getattr(args, "order", None)) and args.type not in _ORDER_CHARTS,
         "--order 仅 bar/box/violin/line 系生效"),
        (bool(getattr(args, "normalize", None)) and args.type not in _NORM_CHARTS,
         "--normalize 仅 bar 系/line 生效（分布数据不做均值归一）"),
        (bool(args.journal) and bool(args.width),
         "--journal 会锁定图宽，--width 将被覆盖（去掉 --width 或改用 --column）"),
    ]
    for bad, msg in combos:
        if bad:
            issues += 1
            print(f"  [!] {msg}", file=sys.stderr)
    try:
        fatal, warns = validate_data(data, args.type)
        if fatal:
            issues += len(fatal)
            for m in fatal:
                print(f"  [!] 数据致命: {m}", file=sys.stderr)
        else:
            print(f"  [ok] 数据结构校验通过（{args.type}）"
                  + (f"；{len(warns)} 条警告" if warns else ""), file=sys.stderr)
    except Exception as e:
        issues += 1
        print(f"  [!] 数据校验异常: {e}", file=sys.stderr)
    for mod, hint in (("numpy", "numpy"), ("matplotlib", "matplotlib"),
                      ("scipy", "scipy（仅 --stats 需要）")):
        try:
            importlib.import_module(mod)
        except Exception:
            print(f"  [!] 缺依赖 {hint}", file=sys.stderr)
            issues += 1
    if args.out:
        od = os.path.dirname(os.path.abspath(args.out))
        if not os.path.isdir(od):
            issues += 1
            print(f"  [!] 输出目录不存在: {od}", file=sys.stderr)
        elif not os.access(od, os.W_OK):
            issues += 1
            print(f"  [!] 输出目录不可写: {od}", file=sys.stderr)
        else:
            print(f"  [ok] 输出目录可写: {od}", file=sys.stderr)

    def _scan(o):
        if isinstance(o, str):
            return has_cjk(o)
        if isinstance(o, dict):
            return any(_scan(k) or _scan(v) for k, v in o.items())
        if isinstance(o, (list, tuple)):
            return any(_scan(v) for v in o)
        return False

    if any(has_cjk(t) for t in (args.title, args.xlabel, args.ylabel) if t) or _scan(data):
        print("  [i] 检测到中文文本——将自动加载 CJK 字体（--cjk 可显式指定）", file=sys.stderr)
    print(f"── doctor 完成：{'✅ 未发现问题' if issues == 0 else f'⚠️ {issues} 项需注意'} ──",
          file=sys.stderr)
    return issues


def validate_data(data, chart_type):









    fatal, warns = [], []

    if not isinstance(data, dict):
        fatal.append("数据必须是非空 JSON 对象，或由 CSV 转换来的字典")
        return fatal, warns

    def _nonempty_list(v):
        return isinstance(v, (list, tuple)) and len(v) > 0

    def _len(v):
        return len(v) if isinstance(v, (list, tuple)) else 0

    def _warn_flat(name, vals):

        fvals = [float(v) for v in vals if _is_number(v)]
        if len(fvals) >= 2 and max(fvals) == min(fvals):
            warns.append(
                f"系列 '{name}' 的值全部相同（恒为 {fvals[0]:g}）— 图会是一条平线。"
                f"请确认这是数据本意，而不是取错了列")

    def _warn_non_numeric(name, vals):
        n_bad = sum(1 for v in vals if not _is_number(v))
        if n_bad:
            warns.append(
                f"系列 '{name}' 里有 {n_bad} 个非数值项，画图时会跳过 — "
                f"请检查源数据里是否混入了 'NA'、'—' 或文字")

    def _check_series_dict(series, err_key, req_nonempty=True):

        msgs = []
        if not isinstance(series, dict):
            msgs.append(f"'{err_key}' 必须是 JSON 对象（形如 {{\"系列名\": [数值, ...]}}）— 当前类型不符")
            return msgs
        if req_nonempty and not series:
            msgs.append(f"'{err_key}' 是空的 — 至少要有一个系列（一组名称+数值数组）")
            return msgs
        empty_names = [n for n, v in series.items() if not _nonempty_list(v)]
        if empty_names:
            msgs.append(f"'{err_key}' 里这些系列没有数据: {empty_names[:3]}"
                        f"{'...' if len(empty_names) > 3 else ''} — 空系列无法画，请删掉或补数据")
        for n, v in series.items():
            if _nonempty_list(v):
                _warn_non_numeric(n, v)
                _warn_flat(n, v)
        return msgs

    
    if chart_type in ("bar", "grouped_bar", "hbar", "horizontal_bar", "line",
                      "stacked_bar", "box", "boxplot", "violin"):
        series = data.get("series", data.get("datasets", {}))
        fatal += _check_series_dict(series, "series")
        labels = data.get("labels", data.get("x", []))
        is_boxlike = chart_type in ("box", "boxplot", "violin")
        if _nonempty_list(labels) and series:
            if is_boxlike:
                
                
                n_labels, n_groups = _len(labels), len(series)
                if n_labels != n_groups:
                    fatal.append(
                        f"labels 有 {n_labels} 个组名但 series 有 {n_groups} 组 — "
                        f"每个箱线/小提琴图恰好对应一个组名，数量对不上多半是 labels 和数据错位了")
            else:
                n_labels, n_first = _len(labels), _len(next(iter(series.values())))
                if n_labels != n_first:
                    fatal.append(
                        f"labels 有 {n_labels} 项但系列值只有 {n_first} 个 — "
                        f"长度不齐会导致图内容被静默截断，请修正 CSV/JSON 对齐。")
        elif not is_boxlike and not _nonempty_list(labels):
            warns.append("未提供 labels：x 轴将使用序号 0..n-1")
        
        errs = data.get("errors", {})
        if isinstance(errs, dict) and errs:
            unknown = [k for k in errs if k not in series]
            if unknown:
                warns.append(f"errors 引用了数据里不存在的系列: {unknown[:3]}")
            for n, v in errs.items():
                if n in series and _nonempty_list(v) and _len(v) != _len(series[n]):
                    warns.append(f"errors['{n}'] 有 {_len(v)} 个值但系列 '{n}' 有 {_len(series[n])} 个 — 数量应一一对应，误差棒可能错位")
        
        sig = data.get("significance", {})
        if isinstance(sig, dict) and sig:
            unknown = [k for k in sig if k not in series]
            if unknown:
                warns.append(f"significance 引用了数据里不存在的系列: {unknown[:3]}")

    
    elif chart_type == "heatmap":
        matrix = data.get("matrix", data.get("data", data.get("values")))
        if matrix is None:
            fatal.append("heatmap 需要 'matrix'（二维数值数组）— 数据里没有这个字段")
        elif not isinstance(matrix, (list, tuple)) or len(matrix) == 0:
            fatal.append("heatmap: 'matrix' 为空 — 请提供二维数组")
        elif not all(isinstance(r, (list, tuple)) and _len(r) == _len(matrix[0]) for r in matrix):
            fatal.append("heatmap: 'matrix' 各行长度不一致（参差行）— 每行单元格数必须相同")
        else:
            flat = [float(x) for r in matrix for x in r if _is_number(x)]
            n_bad = sum(1 for r in matrix for x in r if not _is_number(x))
            if n_bad:
                warns.append(f"heatmap: {n_bad} 个非数值单元格将渲染为空白/NaN")
            if flat and max(flat) == min(flat):
                warns.append(f"heatmap: 全部 {len(flat)} 个单元格值相同（{flat[0]:g}）— 热图将是单一颜色，请核对数据")

    
    elif chart_type == "scatter":
        x = data.get("x", data.get("xs", []))
        y = data.get("y", data.get("ys", []))
        if not _nonempty_list(x):
            fatal.append("scatter 需要 'x'（数值数组）— 字段缺失或为空")
        if not _nonempty_list(y):
            fatal.append("scatter 需要 'y'（数值数组）— 字段缺失或为空")
        if not fatal:
            if _len(x) != _len(y):
                fatal.append(f"scatter: 'x' 有 {_len(x)} 个值但 'y' 有 {_len(y)} 个 — 每个点需要一对 x/y，长度必须一致")
            _warn_non_numeric("x", x)
            _warn_non_numeric("y", y)
            if len(x) >= 2 and _is_number(x[0]) and _is_number(x[-1]) and max(float(v) for v in x if _is_number(v)) == min(float(v) for v in x if _is_number(v)):
                warns.append("scatter: 所有 x 值相同 — 点将垂直堆叠，趋势线（若显示）无意义")
        groups = data.get("groups", data.get("colors"))
        if groups is not None and not _nonempty_list(groups):
            fatal.append("scatter: 'groups' 存在但为空")
        elif groups is not None and _len(groups) != _len(x) and _len(groups) > 0:
            warns.append(f"scatter: 'groups' 有 {_len(groups)} 项但共 {_len(x)} 个点 — 分组可能错位")

    
    elif chart_type == "forest":
        estimates = data.get("estimates", data.get("values", []))
        ci_low = data.get("ci_low", data.get("lower", []))
        ci_high = data.get("ci_high", data.get("upper", []))
        if not _nonempty_list(estimates):
            fatal.append("forest 需要 'estimates'（各研究效应值）— 字段缺失或为空")
        if not _nonempty_list(ci_low):
            fatal.append("forest 需要 'ci_low'（各研究 CI 下限）— 字段缺失或为空")
        if not _nonempty_list(ci_high):
            fatal.append("forest 需要 'ci_high'（各研究 CI 上限）— 字段缺失或为空")
        if not fatal:
            if not (_len(estimates) == _len(ci_low) == _len(ci_high)):
                fatal.append(f"forest: estimates/ci_low/ci_high 长度不一致（{_len(estimates)}/{_len(ci_low)}/{_len(ci_high)}）— 每个研究都要三个值")
            _warn_non_numeric("estimates", estimates)
            for i in range(min(_len(estimates), _len(ci_low), _len(ci_high))):
                if _is_number(estimates[i]) and _is_number(ci_low[i]) and _is_number(ci_high[i]):
                    if not (float(ci_low[i]) <= float(estimates[i]) <= float(ci_high[i])):
                        warns.append(f"forest: 研究 {i} 的效应值 {estimates[i]:g} 落在 CI [{ci_low[i]:g}, {ci_high[i]:g}] 之外 — 请核对数据")
        labels = data.get("labels", data.get("studies", []))
        if _nonempty_list(labels) and _len(labels) != _len(estimates):
            warns.append(f"forest: {_len(labels)} 个研究标签但 {_len(estimates)} 个效应值 — 标签可能错位")
        weights = data.get("weights")
        if _nonempty_list(weights) and _len(weights) != _len(estimates):
            warns.append(f"forest: {_len(weights)} 个权重但 {_len(estimates)} 个效应值 — 气泡大小可能错配")
        events = data.get("events")
        if isinstance(events, list) and events and _len(events) != _len(estimates):
            warns.append(f"forest: {_len(events)} 行事件数据但 {_len(estimates)} 个效应值 — events/total 可能错位")

    
    elif chart_type in ("km", "survival"):
        groups = data.get("groups", data.get("series", {}))
        has_time = _nonempty_list(data.get("time", []))
        if isinstance(groups, dict) and groups and all(isinstance(v, (list, tuple)) and v and all(isinstance(p, (list, tuple)) and _len(p) >= 2 for p in v) for v in groups.values()):
            for gname, pairs in groups.items():
                times = [p[0] for p in pairs if _is_number(p[0])]
                if len(times) >= 2 and any(times[i] > times[i + 1] for i in range(len(times) - 1)):
                    warns.append(f"km: 组 '{gname}' 时间点未升序 — 拟合前已自动排序，曲线不受影响")
        elif has_time and isinstance(data.get("survival"), dict):
            surv = data["survival"]
            fatal += _check_series_dict(surv, "survival", req_nonempty=False)
            for gname, s in surv.items():
                if _nonempty_list(s) and _len(s) != _len(data["time"]):
                    fatal.append(f"km: survival['{gname}'] 有 {_len(s)} 个值但 'time' 有 {_len(data['time'])} 个 — 长度必须一致")
        elif isinstance(groups, dict) and groups:
            
            
            
            _long_keys = {"time", "event", "status", "group", "groups"}
            _keys_l = {str(k).strip().lower() for k in groups}
            if _keys_l & _long_keys:
                fatal.append(
                    "km: 检测到长表结构（time/event/group 各占一列，一行记录一名患者）—"
                    "这种表无法直接画生存曲线。请转成 JSON："
                    '{"groups": {"组名": [[时间, 事件(1=事件/0=删失), ...]], ...}}，'
                    "每组一个数组；格式详见 references/data-formats.md")
            else:
                fatal.append(
                    "km: groups 的每个值必须是 [时间, 事件(1/0)] 成对列表，当前是普通数值数组 —"
                    '请改为 {"组名": [[12, 1], [24, 0], ...]}，或改用 time+survival 两个数组')
        elif not isinstance(groups, dict) or not groups:
            fatal.append("km 需要 'groups'（{组名: [[t, s], ...]}）或 'time'+'survival' 数组 — 都没找到")

    
    elif chart_type == "roc":
        curves = data.get("curves", [])
        fpr = data.get("fpr", data.get("x", []))
        tpr = data.get("tpr", data.get("y", []))
        if _nonempty_list(curves):
            has_scores_mode = data.get("labels") is not None and all(
                isinstance(c, dict) and _nonempty_list(c.get("scores")) for c in curves)
            for i, c in enumerate(curves):
                if not isinstance(c, dict) or not (_nonempty_list(c.get("fpr")) and _nonempty_list(c.get("tpr"))):
                    if has_scores_mode:
                        continue  
                    fatal.append(f"roc: curves[{i}] 必须有 'fpr' 和 'tpr' 数组（--compare 模式可用 labels+scores）")
                elif _len(c["fpr"]) != _len(c["tpr"]):
                    fatal.append(f"roc: curves[{i}] fpr/tpr 长度不一致（{_len(c['fpr'])}/{_len(c['tpr'])}）")
                else:
                    f = [float(v) for v in c["fpr"] if _is_number(v)]
                    if len(f) >= 2 and any(f[i] > f[i + 1] + 1e-9 for i in range(len(f) - 1)):
                        warns.append(f"roc: curves[{i}] fpr 非单调 — 请按阈值排序曲线")
                c_auc = c.get("auc")
                if isinstance(c_auc, (int, float)) and not (0.0 <= float(c_auc) <= 1.0):
                    warns.append(f"roc: curves[{i}] auc={c_auc:g} 超出 [0, 1] — 请核对该值")
        elif _nonempty_list(fpr) and _nonempty_list(tpr):
            if _len(fpr) != _len(tpr):
                fatal.append(f"roc: fpr 有 {_len(fpr)} 个但 tpr 有 {_len(tpr)} 个 — 长度必须一致")
            _warn_non_numeric("fpr", fpr)
            _warn_non_numeric("tpr", tpr)
        else:
            fatal.append("roc 需要 'curves'（{fpr,tpr} 列表）或 'fpr'+'tpr' 数组 — 都没找到")
        auc = data.get("auc")
        if isinstance(auc, (int, float)) and not (0.0 <= float(auc) <= 1.0):
            warns.append(f"roc: auc={auc:g} 超出 [0, 1] — 请核对该值")

    
    elif chart_type == "dual_axis":
        labels = data.get("labels", data.get("x", []))
        left = data.get("left", data.get("y1", {}))
        right = data.get("right", data.get("y2", {}))
        fatal += _check_series_dict(left, "left/y1")
        fatal += _check_series_dict(right, "right/y2")
        if not fatal and _nonempty_list(labels) and left and right:
            n_first = _len(next(iter(left.values())))
            if _len(labels) != n_first:
                fatal.append(f"dual_axis: labels 有 {_len(labels)} 项但 left/right 系列有 {n_first} 个 — 长度必须一致")

    
    elif chart_type == "slope":
        items = data.get("items")
        if not isinstance(items, dict) or len(items) < 2:
            fatal.append("slope: 需要 'items'（至少 2 项，每项 [左值, 右值]）")
        else:
            for n, v in items.items():
                if not (isinstance(v, (list, tuple)) and len(v) == 2
                        and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                for x in v)):
                    fatal.append(f"slope: items['{n}'] 必须是恰好 2 个数值 [左值, 右值]")

    
    elif chart_type == "volcano":
        l2 = data.get("log2fc")
        pv = data.get("pvalue")
        if not (isinstance(l2, list) and isinstance(pv, list)) or not l2 or len(l2) != len(pv):
            fatal.append("volcano: 需要 'log2fc' 与 'pvalue' 两个等长数值数组")
        else:
            if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in l2 + pv):
                fatal.append("volcano: log2fc/pvalue 必须全为数值")
            else:
                bad_p = [p for p in pv if not (0 < p <= 1)]
                if bad_p:
                    fatal.append(f"volcano: pvalue 必须在 (0, 1]（发现 {len(bad_p)} 个越界值，"
                                 "p=0 请用最小可表示值如 1e-300）")
        names = data.get("names")
        if names is not None and (not isinstance(names, list) or len(names) != len(l2 or [])):
            fatal.append("volcano: 'names' 长度必须与 log2fc 一致")

    
    elif chart_type == "composite":
        panels = data.get("panels", [])
        if not isinstance(panels, list) or not panels:
            fatal.append("composite 需要 'panels'（非空面板对象列表）")
        else:
            bad = [i for i, p in enumerate(panels) if not isinstance(p, dict) or not p.get("type")]
            if bad:
                fatal.append(f"composite: 面板 {bad[:5]} 缺少 'type' 字段 — 每个面板都要有 type（如 'bar'）")
            
            lay = data.get("layout", [1, 2])
            _nr, _nc = int(lay[0]), int(lay[1])
            occ = {}
            for i, p in enumerate(panels):
                if not isinstance(p, dict):
                    continue
                if "pos" not in p:
                    continue  
                pos = p.get("pos")
                if not (isinstance(pos, list) and len(pos) == 2
                        and all(isinstance(x, int) for x in pos)):
                    continue
                r0, c0 = pos
                if not (0 <= r0 < _nr and 0 <= c0 < _nc):
                    fatal.append(f"composite: 面板 {i} pos {pos} 超出 layout {[_nr, _nc]}")
                    continue
                sp = p.get("span", [1, 1]) or [1, 1]
                if not (isinstance(sp, list) and len(sp) == 2
                        and all(isinstance(x, int) and x >= 1 for x in sp)):
                    fatal.append(f"composite: 面板 {i} span 必须是 ≥1 的整数 [行, 列]")
                    continue
                rs = min(sp[0], _nr - r0)
                cs = min(sp[1], _nc - c0)
                for r in range(r0, r0 + rs):
                    for c in range(c0, c0 + cs):
                        if (r, c) in occ:
                            fatal.append(f"composite: 面板 {occ[(r, c)]} 与面板 {i} 在 "
                                         f"({r}, {c}) 占位重叠——span 布局不得交叠")
                            break
                        occ[(r, c)] = i
                    if (r, c) in occ and len(fatal) and "占位重叠" in fatal[-1]:
                        break

    
    elif chart_type == "diagram":
        blocks = data.get("blocks", [])
        if not isinstance(blocks, list) or not blocks:
            fatal.append("diagram 需要 'blocks'（非空块对象列表）")

    
    elif chart_type == "prisma":
        req_ints = ["records_identified", "studies_included"]
        opt_ints = ["duplicates_removed", "records_screened", "records_excluded",
                    "reports_sought", "reports_not_retrieved", "reports_assessed"]
        vals = {}
        for k in req_ints + opt_ints:
            v = data.get(k)
            if v is None:
                continue
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                fatal.append(f"prisma '{k}' 必须是非负整数（当前 {v!r}）")
            else:
                vals[k] = v
        for k in req_ints:
            if k not in vals:
                fatal.append(f"prisma 缺少 '{k}'（非负整数）")
        
        
        ident = vals.get("records_identified")
        dup = vals.get("duplicates_removed", 0)
        screened = vals.get("records_screened")
        if screened is None and ident is not None:
            screened = ident - dup
        excluded = vals.get("records_excluded", 0)
        sought = vals.get("reports_sought")
        if sought is None and screened is not None:
            sought = screened - excluded
        not_ret = vals.get("reports_not_retrieved", 0)
        assessed = vals.get("reports_assessed")
        if assessed is None and sought is not None:
            assessed = sought - not_ret
        if ident is not None and vals.get("records_screened") is not None \
                and vals["records_screened"] != ident - dup:
            fatal.append(f"prisma 数字自洽校验失败: records_screened ({vals['records_screened']}) != "
                         f"records_identified - duplicates_removed ({ident - dup})")
        if vals.get("reports_sought") is not None and screened is not None \
                and vals["reports_sought"] != screened - excluded:
            fatal.append(f"prisma 数字自洽校验失败: reports_sought ({vals['reports_sought']}) != "
                         f"records_screened - records_excluded ({screened - excluded})")
        if vals.get("reports_assessed") is not None and sought is not None \
                and vals["reports_assessed"] != sought - not_ret:
            fatal.append(f"prisma 数字自洽校验失败: reports_assessed ({vals['reports_assessed']}) != "
                         f"reports_sought - reports_not_retrieved ({sought - not_ret})")
        reasons = data.get("exclusion_reasons")
        if reasons is not None:
            if not isinstance(reasons, dict) or not reasons:
                fatal.append("prisma 'exclusion_reasons' 必须是非空对象 {原因: 数量}")
            else:
                bad = {r: n for r, n in reasons.items()
                       if isinstance(n, bool) or not isinstance(n, int) or n < 0}
                if bad:
                    fatal.append(f"prisma exclusion_reasons 的值必须是非负整数，"
                                 f"这些键有问题: {bad}")
                total = sum(n for n in reasons.values()
                            if isinstance(n, int) and not isinstance(n, bool))
                inc = vals.get("studies_included")
                if assessed is not None and inc is not None and total + inc != assessed:
                    fatal.append(f"prisma 数字自洽校验失败: exclusion_reasons 总数 ({total}) + "
                                 f"studies_included ({inc}) != reports_assessed ({assessed}) "
                                 f"— 排除人数+纳入数应等于评估全文数，请复核流程数字")
        lang = data.get("lang")
        if lang is not None and lang not in ("en", "zh"):
            fatal.append("prisma 'lang' 只能是 'en' 或 'zh'")

    if _afcharts is not None and chart_type in _afcharts.EXTRA_GENERATORS:
        f23, w23 = _afcharts.validate_extra(chart_type, data)
        fatal.extend(f23)
        warns.extend(w23)

    return fatal, warns


def legend_audit(ax, chart_type, no_legend, n_series):








    if no_legend or chart_type in ("box", "boxplot", "violin", "heatmap", "forest",
                                   "composite", "diagram", "dual_axis"):
        return None
    if n_series < 2:
        return None
    handles, labels = ax.get_legend_handles_labels()
    if not any(labels):
        return ("绘制了多个系列但没有一个带 label — 图例将为空；"
                "请在 JSON 里给系列加 name 键（或 CSV 用分组列）以便区分")
    return None





if _afcharts is not None:
    GENERATORS.update(_afcharts.EXTRA_GENERATORS)
    DEMO_DATA.update(_afcharts.EXTRA_DEMO_DATA)

_EXC_ZH = {
    "KeyError": "缺少必需字段",
    "BadZipFile": "文件不是有效的压缩/xlsx 格式",
    "JSONDecodeError": "不是合法的 JSON 文本",
    "ValueError": "数值/格式不符合要求",
    "FileNotFoundError": "文件不存在或路径不对",
    "PermissionError": "文件被占用或没有写入权限",
    "UnicodeDecodeError": "文件编码不是 UTF-8/ASCII（请转存为 UTF-8）",
    "TypeError": "数据类型不匹配",
    "IndexError": "数据行/列数量不足",
    
    "MemoryError": "数据规模超出可用内存（请减小数据量或分批处理）",
    "OverflowError": "数值溢出（数据量级过大或含极端值）",
    "ZeroDivisionError": "出现除零（数据退化：全为常数或完全相同）",
    "ParserError": "CSV/表格解析失败（行列数不齐或格式错乱）",
    "InvalidFileException": "不是有效的 xlsx 文件（或已损坏）",
    "AttributeError": "数据结构与该图型要求不符",
    "ModuleNotFoundError": "缺少依赖库（按提示 pip install 即可）",
    "IsADirectoryError": "给的是目录路径，需要的是文件",
    "StopIteration": "数据为空或已耗尽（检查文件内容是否为空）",
}


def _zh_exception(e: BaseException) -> str:

    name = type(e).__name__
    head = _EXC_ZH.get(name, f"{name}")
    return f"{head}（{name}: {e}）"




_LEGEND_LOCS = {"best", "upper right", "upper left", "lower left", "lower right",
                "right", "center left", "center right", "lower center",
                "upper center", "center"}


def _parse_annotations(items):

    out = []
    for raw in items or []:
        s = str(raw)
        if ":" not in s:
            raise ValueError(f'--annotate 语法为 "x,y:文字"（缺少冒号）：{raw}')
        coord, text = s.split(":", 1)
        parts = coord.split(",")
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            raise ValueError(f'--annotate 坐标需为 "x,y"（数字或类别刻度标签）：{raw}')
        text = text.strip()
        if not text:
            raise ValueError(f"--annotate 注释文字不能为空：{raw}")
        out.append((parts[0].strip(), parts[1].strip(), text, s))
    return out


def _resolve_coord(axes, value, which):

    s = str(value).strip()
    try:
        return float(s)
    except ValueError:
        pass
    if which == "x":
        labels, ticks = axes.get_xticklabels(), axes.get_xticks()
    else:
        labels, ticks = axes.get_yticklabels(), axes.get_yticks()
    for i, t in enumerate(labels):
        if t.get_text().strip() == s:
            try:
                return float(ticks[i])
            except (TypeError, ValueError, IndexError):
                return None
    return None


def _apply_annotations(fig, anns, theme, cjk_fp):







    if not anns:
        return cjk_fp
    import math as _m
    import matplotlib.patches as _mpatches

    def _try_axes(a):
        resolved = []
        
        xa, xb = sorted(a.get_xlim())
        ya, yb = sorted(a.get_ylim())
        for xs, ys, _t, _raw in anns:
            px = _resolve_coord(a, xs, "x")
            py = _resolve_coord(a, ys, "y")
            if px is None or py is None:
                return None
            if not (xa - 0.02 * (xb - xa) <= px <= xb + 0.02 * (xb - xa)):
                return None
            if not (ya - 0.02 * (yb - ya) <= py <= yb + 0.02 * (yb - ya)):
                return None
            resolved.append((px, py))
        return resolved

    def _data_score(a):
        
        return (len(a.lines) * 10 + len(a.collections) * 10 + len(a.images) * 10
                + len(a.containers) * 5 + len(a.patches))

    target, resolved = None, None
    for a in sorted(fig.axes, key=_data_score, reverse=True):
        r = _try_axes(a)
        if r is not None:
            target, resolved = a, r
            break
    if target is None:
        a = fig.axes[0] if fig.axes else None
        detail = ""
        if a is not None:
            xl = [t.get_text() for t in a.get_xticklabels() if t.get_text()][:8]
            xa, xb = sorted(a.get_xlim())
            ya, yb = sorted(a.get_ylim())
            detail = (f"（x 轴范围 {xa:.4g}~{xb:.4g}"
                      + (f"，类别刻度: {','.join(xl)}" if xl else "")
                      + f"；y 轴范围 {ya:.4g}~{yb:.4g}）")
        print(f"ERROR: --annotate 无法定位坐标，请确认落在图表数据范围内{detail}",
              file=sys.stderr)
        sys.exit(1)

    
    if cjk_fp is None and any(has_cjk(t) for _x, _y, t, _r in anns):
        try:
            cjk_fp, cjk_name = load_cjk_font(None)
            if cjk_fp:
                plt.rcParams['font.sans-serif'] = [cjk_name, 'DejaVu Sans'] \
                    + plt.rcParams['font.sans-serif']
                plt.rcParams['axes.unicode_minus'] = False
                print(f"自动补启用中文字体: {cjk_name}（--annotate 含中文）", file=sys.stderr)
        except Exception:
            pass

    x0, x1 = target.get_xlim()
    y0, y1 = target.get_ylim()
    span = min(abs(x1 - x0), abs(y1 - y0)) or 1.0
    fs = theme["font_size"]
    texts, arrows, anchors = [], [], []
    for k, ((px, py), (_xs, _ys, txt, _raw)) in enumerate(zip(resolved, anns)):
        ang = 2.399 * k
        ox, oy = span * 0.07 * _m.cos(ang), span * 0.07 * _m.sin(ang)
        t = target.text(px + ox, py + oy, txt, fontsize=fs, ha="center", va="center",
                        color="#333333", zorder=8,
                        fontproperties=cjk_fp if cjk_fp and has_cjk(txt) else None)
        arr = _mpatches.FancyArrowPatch((px + ox, py + oy), (px, py),
                                        arrowstyle="-|>", mutation_scale=fs * 0.9,
                                        color="#555555", linewidth=0.9,
                                        shrinkA=fs * 0.55, shrinkB=1.5, zorder=7)
        target.add_patch(arr)
        texts.append(t)
        arrows.append(arr)
        anchors.append((px, py))
    
    if _afcharts is not None and len(texts) >= 2:
        _afcharts._declutter_texts(target, texts, anchors, leader_min_frac=10.0)
    for arr, t, (ax_, ay_) in zip(arrows, texts, anchors):
        tx, ty = t.get_position()
        arr.set_positions((tx, ty), (ax_, ay_))
    return cjk_fp


def _apply_legend_control(fig, loc=None, outside=False, theme=None, cjk_fp=None):





    if not loc and not outside:
        return
    entries = []
    for a in fig.axes:
        hs, ls = a.get_legend_handles_labels()
        leg = a.get_legend()
        title = leg.get_title().get_text() if leg is not None else ""
        ncols = getattr(leg, "_ncols", None) or getattr(leg, "_ncol", None) or 1
        if leg is not None:
            leg.remove()
        if hs:
            entries.append((a, hs, ls, title, int(ncols)))
    if not entries:
        print("WARNING: 图中本无图例（--legend-loc/--legend-outside 未生效）",
              file=sys.stderr)
        return
    fs = (theme or {}).get("font_size", 10) - 1
    if outside and len(entries) >= 2:
        seen, hs_all, ls_all = set(), [], []
        for _a, hs, ls, _t, _n in entries:
            for h, l in zip(hs, ls):
                if l not in seen:
                    seen.add(l)
                    hs_all.append(h)
                    ls_all.append(l)
        fig.legend(hs_all, ls_all, loc="center left", bbox_to_anchor=(1.0, 0.5),
                   framealpha=0.9, fontsize=fs, prop=cjk_fp if cjk_fp else None)
        print(f"已合并 {len(entries)} 个面板的图例为全图共享图例（右侧）", file=sys.stderr)
        return
    for a, hs, ls, title, ncols in entries:
        kw = {}
        if title:
            kw["title"] = title
        if ncols > 1:
            kw["ncols"] = ncols
        if outside:
            a.legend(hs, ls, loc="center left", bbox_to_anchor=(1.02, 0.5),
                     framealpha=0.9, fontsize=fs, prop=cjk_fp if cjk_fp else None, **kw)
        else:
            a.legend(hs, ls, loc=loc, framealpha=0.9, fontsize=fs,
                     prop=cjk_fp if cjk_fp else None, **kw)




def _run_batch_items(items, manifest_path):

    results = []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or not all(k in item for k in ("type", "data", "out")):
            results.append({"index": i, "ok": False, "error": "缺少 type/data/out 字段"})
            print(f"[batch {i+1}/{len(items)}] FAIL: 缺少 type/data/out 字段", file=sys.stderr)
            continue
        argv = [sys.executable, os.path.abspath(__file__),
                "-t", str(item["type"]), "-d", str(item["data"]), "-o", str(item["out"])]
        for key, flag in (("title", "--title"), ("xlabel", "--xlabel"), ("ylabel", "--ylabel"),
                          ("theme", "--theme"), ("journal", "--journal"), ("column", "--column"),
                          ("stats", "--stats"), ("sheet", "--sheet"), ("risk_times", "--risk-times"),
                          ("legend_loc", "--legend-loc")):
            if item.get(key):
                argv.extend([flag, str(item[key])])
        for key, flag in (("alt", "--alt"), ("caption", "--caption"), ("egger", "--egger"),
                          ("compare", "--compare"), ("cjk", "--cjk"), ("hatch", "--hatch"),
                          ("show_values", "--show-values"), ("no_legend", "--no-legend"),
                          ("no_risk_table", "--no-risk-table"), ("area", "--area"),
                          ("legend_outside", "--legend-outside")):
            if item.get(key):
                argv.append(flag)
        for ann in (item.get("annotate") or []):
            argv.extend(["--annotate", str(ann)])
        for key, flag in (("dpi", "--dpi"), ("width", "--width"), ("height", "--height"),
                          ("timeout", "--timeout"), ("downsample", "--downsample")):
            if item.get(key):
                argv.extend([flag, str(item[key])])
        if item.get("multi_format"):
            argv.extend(["--multi-format", str(item["multi_format"])])
        elif item.get("format"):
            argv.extend(["--format", str(item["format"])])
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=300)
            out_path = str(item["out"])
            _cands = [out_path, out_path + "." + str(item.get("format", "png"))]
            for _f in str(item.get("multi_format") or "").replace("，", ",").split(","):
                _f = _f.strip().lower()
                if _f:
                    _cands.append(out_path + "." + _f)
            ok = proc.returncode == 0 and any(os.path.exists(c) for c in _cands)
            tail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else ""
        except subprocess.TimeoutExpired:
            ok, tail = False, "超时（>300s）"
        results.append({"index": i, "out": str(item["out"]), "ok": ok, "stderr_tail": tail})
        print(f"[batch {i+1}/{len(items)}] {'OK' if ok else 'FAIL'}: {item['out']}",
              file=sys.stderr)
    n_ok = sum(1 for r in results if r["ok"])
    report = {"total": len(items), "ok": n_ok, "failed": len(items) - n_ok, "items": results}
    rpt_path = os.path.splitext(str(manifest_path))[0] + ".batch-report.json"
    try:
        with open(rpt_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"batch: {n_ok}/{len(items)} 成功，报告 {rpt_path}", file=sys.stderr)
    except OSError as e:
        print(f"WARNING: 批量报告写出失败：{e}", file=sys.stderr)
    if n_ok < len(items):
        sys.exit(2)


def cmd_pipeline(pipeline_path):














    ext = os.path.splitext(str(pipeline_path))[1].lower()
    if ext in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            print("ERROR: YAML 流水线需要 PyYAML —— 先运行 pip install pyyaml；"
                  "或改用 JSON 流水线 / --batch（无额外依赖）", file=sys.stderr)
            sys.exit(1)
        try:
            with open(pipeline_path, encoding="utf-8") as f:
                spec = yaml.safe_load(f)
        except Exception as e:
            print(f"ERROR: 流水线 YAML 解析失败：{e}", file=sys.stderr)
            sys.exit(1)
    elif ext == ".json":
        try:
            with open(pipeline_path, encoding="utf-8") as f:
                spec = json.load(f)
        except Exception as e:
            print(f"ERROR: 流水线 JSON 读取失败：{e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("ERROR: 流水线文件需为 .yaml / .yml / .json", file=sys.stderr)
        sys.exit(1)
    if isinstance(spec, list):
        defaults, figures = {}, spec
    elif isinstance(spec, dict):
        figures = spec.get("figures")
        defaults = spec.get("defaults") or {}
    else:
        figures, defaults = None, {}
    if not isinstance(figures, list) or not figures:
        print("ERROR: 流水线需为非空列表，或含非空 'figures' 列表的对象"
              "（可选 'defaults' 全局默认）", file=sys.stderr)
        sys.exit(1)
    if not isinstance(defaults, dict):
        print("ERROR: 'defaults' 必须是对象（键值对形式的全局默认）", file=sys.stderr)
        sys.exit(1)
    base_dir = os.path.dirname(os.path.abspath(pipeline_path))
    items = []
    for fig in figures:
        if not isinstance(fig, dict):
            print(f"ERROR: figures 里的条目必须是对象，得到 {type(fig).__name__}",
                  file=sys.stderr)
            sys.exit(1)
        merged = dict(defaults)
        merged.update(fig)
        for k in ("data", "out"):
            v = merged.get(k)
            if isinstance(v, str) and v and not os.path.isabs(v):
                merged[k] = os.path.normpath(os.path.join(base_dir, v))
        items.append(merged)
    print(f"pipeline: {len(items)} 张图（defaults: "
          f"{', '.join(sorted(defaults.keys())) if defaults else '无'}）", file=sys.stderr)
    _run_batch_items(items, pipeline_path)


def cmd_batch(manifest_path):

    try:
        with open(manifest_path, encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        print(f"ERROR: 批量清单读取失败：{e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(items, list) or not items:
        print("ERROR: 批量清单需为非空 JSON 数组（每项含 type/data/out）", file=sys.stderr)
        sys.exit(1)
    _run_batch_items(items, manifest_path)




def _run_cox_forest(args):






    import csv as _csv

    path = args.data
    if not path or not os.path.exists(path):
        print(f"ERROR: 找不到数据文件：{path}", file=sys.stderr)
        sys.exit(1)
    ext = os.path.splitext(path)[1].lower()
    time_col = args.cox_time
    event_col = args.cox_event

    def _is_num_list(seq):
        try:
            return all(np.isfinite(float(v)) for v in seq)
        except (TypeError, ValueError):
            return False

    def _fatal(msg):
        print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(1)

    cov_raw = {}
    if ext == ".json":
        try:
            with open(path, encoding="utf-8-sig") as fh:
                d = json.load(fh)
        except Exception as exc:
            _fatal(f"JSON 解析失败：{exc}")
        if not isinstance(d, dict) or "time" not in d or "event" not in d:
            _fatal("Cox 数据 JSON 必须包含 time 与 event 两个数组（逐例一行）")
        if isinstance(d.get("covariates"), dict):
            cov_raw = {k: v for k, v in d["covariates"].items()}
        else:
            cov_raw = {k: v for k, v in d.items()
                       if k not in ("time", "event") and isinstance(v, list)}
    elif ext in (".csv", ".tsv", ".txt"):
        delim = "\t" if ext == ".tsv" else ","
        try:
            with open(path, encoding="utf-8-sig", newline="") as fh:
                rows = list(_csv.DictReader(fh, delimiter=delim))
        except Exception as exc:
            _fatal(f"CSV 解析失败：{exc}")
        if not rows:
            _fatal("CSV 为空")
        headers = list(rows[0].keys())
        for need in (time_col, event_col):
            if need not in headers:
                _fatal(f"CSV 缺少必需列「{need}」（现有列：{ '、'.join(headers) }）。"
                       f"可用 --cox-time/--cox-event 指定列名")
        def colvals(name):
            return [r[name] for r in rows]
        times_raw = colvals(time_col)
        events_raw = colvals(event_col)
        for name in headers:
            if name in (time_col, event_col):
                continue
            vals = [v for v in colvals(name) if str(v).strip() != ""]
            if _is_num_list(vals):
                cov_raw[name] = [float(v) for v in colvals(name)]
            else:
                uniq = sorted({str(v).strip() for v in vals})
                if len(uniq) == 2:
                    mapping = {uniq[0]: 0, uniq[1]: 1}
                    cov_raw[name] = [mapping.get(str(v).strip()) for v in colvals(name)]
                    if any(v is None for v in cov_raw[name]):
                        _fatal(f"列「{name}」存在无法识别的取值（允许：{'、'.join(uniq)}）")
                    print(f"Cox 编码：{name} → {uniq[0]}=0（参照）、{uniq[1]}=1"
                          f"（该变量 HR 为「{uniq[1]} 相对 {uniq[0]}」）", file=sys.stderr)
                elif len(uniq) > 2:
                    _fatal(f"列「{name}」有 {len(uniq)} 个类目（{ '、'.join(uniq[:4]) }…）——"
                           "多分类请先拆为哑变量（数值列）再提交")
    else:
        _fatal("--stats cox 支持 .json / .csv / .tsv 原始逐例数据；"
               "效应量森林图（已有 HR/OR 点估计）不要加 --stats cox")

    
    if ext == ".json":
        if not _is_num_list(d["time"]) or not _is_num_list(d["event"]):
            _fatal("time/event 必须是数值数组（event 用 0/1）")
        times = [float(v) for v in d["time"]]
        events = [float(v) for v in d["event"]]
        for k, v in list(cov_raw.items()):
            if not _is_num_list(v):
                uniq = sorted({str(s) for s in v})
                if len(uniq) == 2:
                    cov_raw[k] = [1 if str(s) == uniq[1] else 0 for s in v]
                    print(f"Cox 编码：{k} → {uniq[0]}=0（参照）、{uniq[1]}=1", file=sys.stderr)
                else:
                    _fatal(f"协变量「{k}」不是数值数组（类目数 {len(uniq)}）——请先数值化")
        times = [float(v) for v in times]
        events = [float(v) for v in events]
        cov_raw = {k: [float(x) for x in v] for k, v in cov_raw.items()}
    else:
        try:
            times = [float(v) for v in times_raw]
            events = [float(v) for v in events_raw]
        except (TypeError, ValueError):
            _fatal("time/event 列存在非数值内容")

    if args.cox_cols:
        order = [c.strip() for c in str(args.cox_cols).split(",") if c.strip()]
        missing = [c for c in order if c not in cov_raw]
        if missing:
            _fatal(f"--cox-cols 指定了不存在的列：{'、'.join(missing)}")
        cov_raw = {c: cov_raw[c] for c in order}
    if not cov_raw:
        _fatal("没有可用的协变量列——Cox 多因素回归至少需要 1 个数值协变量")

    if _afstats is None:
        _fatal("统计模块 af_v23_stats 加载失败，无法执行 Cox 回归")
    names = list(cov_raw.keys())
    try:
        fit = _afstats.coxph_fit(times, events,
                                 np.column_stack([cov_raw[n] for n in names]),
                                 names=names)
    except ValueError as exc:
        _fatal(str(exc))
    ph = _afstats.cox_ph_test(fit)

    print(f"Cox 多因素回归（Efron 法）：n={fit['n']}，事件数={fit['n_events']}，"
          f"迭代 {fit['iterations']} 次{'收敛' if fit['converged'] else '未完全收敛'}，"
          f"loglik={fit['loglik']:.3f}", file=sys.stderr)
    print(f"{'协变量':<10}{'beta':>9}{'SE':>9}{'HR':>9}{'95%CI':>19}{'p':>10}{'PH-p':>9}",
          file=sys.stderr)
    for i, name in enumerate(names):
        ci = f"[{fit['hr_low'][i]:.3f},{fit['hr_high'][i]:.3f}]"
        print(f"{name:<10}{fit['beta'][i]:>9.4f}{fit['se'][i]:>9.4f}{fit['hr'][i]:>9.3f}"
              f"{ci:>19}{fit['p'][i]:>10.4f}{ph['p'][i]:>9.4f}", file=sys.stderr)
    low_ph = [n2 for n2, pv in zip(names, ph["p"]) if pv == pv and pv < 0.05]
    if low_ph:
        print(f"⚠ PH 提示：{'、'.join(low_ph)} 的比例风险假设近似检验 p<0.05——"
              "该变量效应可能随时间变化（可考虑分层/时变系数/分段 KM 核对）", file=sys.stderr)

    return {
        "labels": names,
        "estimates": [float(v) for v in fit["hr"]],
        "ci_low": [float(v) for v in fit["hr_low"]],
        "ci_high": [float(v) for v in fit["hr_high"]],
        "measure": "HR",
        "ref_line": 1.0,
        "title_note": f"Cox 多因素回归（n={fit['n']}, 事件={fit['n_events']}）",
    }


def main():
    parser = argparse.ArgumentParser(description="academic-figures：一条命令生成投稿级学术图表")
    parser.add_argument("--type", "-t", choices=list(GENERATORS.keys()),
                        help="图型（如 bar/box/violin/km/roc/forest/prisma，--demo 可看菜单）")
    parser.add_argument("--data", "-d", help="输入数据文件（.json / .csv / .tsv / .xlsx）")
    parser.add_argument("--sheet", default=None,
                        help="xlsx 的工作表名（默认取活动工作表）")
    parser.add_argument("--out", "-o", help="输出文件路径（.png / .svg / .pdf / .tiff / .eps）")
    parser.add_argument("--title", default="", help="图标题")
    parser.add_argument("--xlabel", default="", help="x 轴标签")
    parser.add_argument("--ylabel", default="", help="y 轴标签")
    parser.add_argument("--theme", default=None,
                        help="配色主题（默认 glm；--list-themes 查看全部）")
    parser.add_argument("--style", default=None, choices=["glm-hatch", "nature-clean", "glm-brand"],
                        help="快捷风格：'glm-hatch' = GLM 黄蓝斜线风（theme glm + --hatch）；"
                             "'nature-clean' = 顶刊版式（Okabe-Ito 配色+去顶右框线+无网格+无框图例，v3.3）；"
                             "'glm-brand' = 品牌视觉（信号黄对比强化+无网格+同系深色斜纹，v3.3.1）")
    parser.add_argument("--list-themes", action="store_true",
                        help="列出全部配色主题（含色卡预览）后退出")
    parser.add_argument("--theme-swatch", default=None, metavar="THEME",
                        help="渲染某主题的色卡预览图后退出")
    parser.add_argument("--demo", action="store_true",
                        help="交互演示：菜单选图型，用内置示例数据出图")
    parser.add_argument("--wizard", action="store_true",
                        help="选图向导：4 个问题生成完整命令；非交互环境打印决策树")
    parser.add_argument("--explain", default=None, metavar="CHART_TYPE",
                        help="打印某图型的用法说明与限制后退出")
    parser.add_argument("--suggest", action="store_true",
                        help="分析数据文件并推荐可用图型后退出")
    parser.add_argument("--quick", action="store_true",
                        help="一键出图：按数据自动选型并直接渲染（v3.1）")
    parser.add_argument("--cjk", action="store_true", help="启用中文字体（自动探测）")
    parser.add_argument("--cjk-font", default=None, help="指定中文字体文件路径")
    parser.add_argument("--width", type=float, default=None, help="图宽（英寸）")
    parser.add_argument("--height", type=float, default=None, help="图高（英寸）")
    parser.add_argument("--format", "-f", default=None, choices=["png", "svg", "pdf", "tiff", "eps"],
                        help="输出格式（默认按 --out 扩展名自动判断）")
    parser.add_argument("--pub-ready", action="store_true",
                        help="一键投稿包：自动加 --verify + --multi-format pdf,png + 色盲安全主题"
                             "（--pub-ready theme,NAME 可指定主题；v3.8）")
    parser.add_argument("--profile", default=None, metavar="FILE",
                        help="分层配置文件（v4.3）：JSON 预设呈现参数（theme/journal/"
                             "column/dpi/subtitle/source 等，白名单见文档），CLI 显式"
                             "参数优先——一次定义，处处复用")
    parser.add_argument("--peak-label", action="store_true",
                        help="自动峰值注记（v4.2）：最大值点标注\"峰值 X（类目）\"——"
                             "纯数据事实（bar/hbar/line 系）")
    parser.add_argument("--summary", action="store_true",
                        help="自动数据摘要副标题（v4.1）：纯计数事实（样本量/组数/"
                             "事件数等，零推断）；--subtitle 显式给出时以其为准")
    parser.add_argument("--subtitle", default=None,
                        help="副标题（主标题下方第二行，小号灰色——标题层级 v4.0；"
                             "兼容 --title \"主/副\" 斜杠写法）")
    parser.add_argument("--source", default=None,
                        help="来源注（图底部右对齐小字，如\"数据来源：XX 数据库\"——v4.0）")
    parser.add_argument("--order", default=None, metavar="L1,L2,...|auto",
                        help="自定义类别顺序：逗号分隔标签，或 auto=按第一系列值降序"
                             "（box/violin 按各组中位数降序）（v3.9；仅 bar/box/violin/line 系）")
    parser.add_argument("--normalize", default=None, choices=["baseline", "pct100"],
                        help="归一化：baseline=各系列÷第一系列均值（对照=1）；"
                             "pct100=各系列÷自身首点×100（T0=100）（v3.9；仅 bar 系/line）")
    parser.add_argument("--doctor", action="store_true",
                        help="渲染前参数/环境体检报告（组合冲突/数据/依赖/输出目录），"
                             "只报告不改退出码；省略 -o 可只体检不渲染（v3.9）")
    parser.add_argument("--multi-format", default=None, metavar="F1,F2,...",
                        help="一次输出多种格式（逗号分隔 png/svg/pdf/tiff/eps，兼容全角逗号）："
                             "文件名取 --out 去扩展名后逐格式拼接，如 -o fig1 --multi-format tiff,png,pdf "
                             "→ fig1.tiff/fig1.png/fig1.pdf；与 --format 同时给出时以本参数为准")
    parser.add_argument("--dpi", type=int, default=None,
                        help="位图 DPI（默认：线条图 600，照片类 300）")
    parser.add_argument("--legend", action="store_true", default=True, help="显示图例")
    parser.add_argument("--no-legend", action="store_true", help="隐藏图例")
    parser.add_argument("--show-values", action="store_true", help="在图元上标注数值")
    parser.add_argument("--trend", action="store_true", default=True, help="显示趋势线（散点图）")
    parser.add_argument("--no-trend", action="store_true", help="隐藏趋势线（散点图）")
    parser.add_argument("--cmap", default=None, help="热图配色映射（colormap）")
    parser.add_argument("--vmin", type=float, default=None, help="热图色阶下限")
    parser.add_argument("--vmax", type=float, default=None, help="热图色阶上限")
    parser.add_argument("--horizontal", action="store_true", help="水平柱状图（即 hbar）")
    parser.add_argument("--hatch", action="store_true", help="柱体加斜线填充（打印友好）")
    parser.add_argument("--alternate", action="store_true",
                        help="GLM 风格：单系列柱子交替前两种主题色")
    parser.add_argument("--show-ratio", action="store_true", help="分组柱上标注倍率（如 4.96x）")
    parser.add_argument("--ratio-base", type=int, default=0, help="倍率计算的基准系列序号（默认 0）")
    parser.add_argument("--stats", default=None, choices=["auto", "multi", "cox", "bootstrap"],
                        help="box/violin 自动显著性标注：auto=各组 vs 第一组（Shapiro 定正态→"
                             "Welch t / Mann-Whitney U）；multi=全两两（正态→ANOVA+Tukey，"
                             "否则 Kruskal-Wallis+Dunn+Hochberg）。括号+星号自动绘制。"
                             "cox=仅 forest：原始逐例生存数据自动拟合多因素 Cox 比例风险模型，"
                             "输出 HR[95%%CI] 森林图+系数表+PH 假设近似检验")
    parser.add_argument("--timeout", type=float, default=None,
                        help="渲染看门狗预算（秒）：超时强制中断并给中文建议（exit 5）；"
                             "0=禁用；默认按图型与数据量自适应（30~1800s）")
    parser.add_argument("--downsample", type=int, default=None, metavar="N",
                        help="cluster_heatmap 行数超过 N 时等距采样到 N 行（确定性采样）")
    parser.add_argument("--size", default=None,
                        choices=["16:9", "4:5", "3:2", "1:1", "5:4", "9:16"],
                        help="画幅比例预设（宽:高）：16:9 演示/PPT、4:5 与 3:2 通用、"
                             "9:16 手机/社交竖版、1:1 方版。宽度仍由期刊预设/主题决定，"
                             "仅按比例推算高度")
    parser.add_argument("--cox-time", default="time",
                        help="--stats cox 时生存时间列名（默认 time）")
    parser.add_argument("--cox-event", default="event",
                        help="--stats cox 时事件列名（默认 event；0=删失 1=事件）")
    parser.add_argument("--cox-cols", default=None,
                        help="--stats cox 时协变量列（逗号分隔，默认除时间/事件外全部数值列；"
                             "顺序即森林图行序）")
    parser.add_argument("--alt", action="store_true",
                        help="输出旁生成无障碍描述文件（<输出名>.alt.txt）")
    parser.add_argument("--caption", action="store_true",
                        help="输出旁生成中英双语期刊式图注文件（<输出名>.caption.txt）")
    parser.add_argument("--sensitivity", action="store_true",
                        help="forest：留一法敏感性分析（省略单研究后的合并效应画在同一图下方；"
                             "需 se_list 或对称 CI 反推）")
    parser.add_argument("--no-median", dest="no_median", action="store_true",
                        help="km：关闭自动中位生存计算与标注")
    parser.add_argument("--compare", action="store_true",
                        help="roc：配对 DeLong 检验比较 >=2 个模型 AUC（需 labels + 各曲线 scores 原始分数）")
    parser.add_argument("--egger", action="store_true",
                        help="funnel：绘制 Egger 回归线并报告漏斗不对称检验")
    parser.add_argument("--area", action="store_true",
                        help="venn：按区域计数比例绘制（Euler 图），替代默认等圆示意")
    parser.add_argument("--annotate", action="append", default=None, metavar='"X,Y:文字"',
                        help="在数据坐标处加箭头注释，可重复使用；类别轴可用刻度标签"
                             "定位（如 --annotate \"3.2,5.1:p=0.01\" 或 \"对照组:显著上调\"）")
    parser.add_argument("--direct-label", action="store_true",
                        help="线图直接标注系列名于线末端（替代图例框，Nature 风格；v3.4）")
    parser.add_argument("--no-direct-label", dest="direct_label", action="store_false",
                        help="关闭直接标注（glm-brand/nature-clean 主题下 line 默认开启）")
    parser.add_argument("--legend-loc", default=None, metavar="LOC",
                        help="图例位置：best/upper right/upper left/lower left/lower "
                             "right/right/center left/center right/center 等九宫格")
    parser.add_argument("--legend-outside", dest="legend_outside", action="store_true",
                        help="图例移到绘图区外侧；组合图自动合并为全图共享图例（右侧）")
    parser.add_argument("--no-risk-table", dest="no_risk_table", action="store_true",
                        help="km：关闭自动风险表（默认开启，位于主图下方）")
    def _risk_times_arg(v):
        try:
            out = [float(x) for x in str(v).replace("，", ",").split(",") if x.strip()]
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"风险表时间点 '{v}' 无法解析为数字（正确示例：2,6,10）")
        if not out:
            raise argparse.ArgumentTypeError("风险表时间点为空（正确示例：2,6,10）")
        return out
    parser.add_argument("--risk-times", default=None, type=_risk_times_arg,
                        metavar="T1,T2,...",
                        help="km：风险表显示时间点（逗号分隔数字；默认 0~最大随访等分 5 档）")
    parser.add_argument("--batch", default=None, metavar="FIGURES.json",
                        help="批量出图：JSON 清单（每项含 type/data/out，可带 title/theme/stats 等），"
                             "逐项渲染后写 .batch-report.json 汇总")
    parser.add_argument("--pipeline", default=None, metavar="ANALYSIS.yaml",
                        help="多图流水线（--batch 升级版）：YAML 或 JSON 描述一篇论文全部图表——"
                             "defaults 全局默认 + figures 逐图条目（type/data/out 必填，可覆盖默认），"
                             "一条命令批量渲染并写 .batch-report.json；相对路径相对流水线文件解析；"
                             "YAML 需先 pip install pyyaml（JSON 无额外依赖）")
    parser.add_argument("--verify", action="store_true",
                        help="对 PDF 输出做像素级文字重叠检查；发现重叠则退出码 2")
    parser.add_argument("--journal", default=None, choices=sorted(JOURNAL_PRESETS.keys()),
                        help="期刊预设（nature/lancet/science/cell/nejm/jama/ieee/cma/cn-core）："
                             "栏宽、字号、最小字号、字体；cma/cn-core 自动启用中文字体")
    parser.add_argument("--column", default="double", choices=["single", "double"],
                        help="--journal 的栏宽版式（默认 double 双栏）")

    args = parser.parse_args()

    
    if getattr(args, "profile", None):
        _PALLOW = {"theme", "style", "journal", "column", "dpi", "width", "height",
                   "title", "subtitle", "source", "xlabel", "ylabel", "cjk", "verify",
                   "legend_loc", "legend_outside", "multi_format", "peak_label",
                   "summary", "alt", "caption", "format"}
        try:
            _prof = json.load(open(args.profile, encoding="utf-8"))
        except Exception as _e:
            print(f"ERROR: --profile 读取失败: {_e}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(_prof, dict):
            print("ERROR: --profile 文件必须是 JSON 对象", file=sys.stderr)
            sys.exit(1)
        _applied = []
        for _k, _v in _prof.items():
            if _k not in _PALLOW:
                print(f"WARNING: --profile 忽略未知键 {_k}（白名单见文档）", file=sys.stderr)
                continue
            if getattr(args, _k, None) in (None, False):
                setattr(args, _k, _v)
                _applied.append(f"{_k}={_v}")
        if _applied:
            print("[profile] 已应用 " + str(len(_applied)) + " 项默认（"
                  + "；".join(_applied[:8]) + ("…" if len(_applied) > 8 else "")
                  + "）；CLI 显式参数优先", file=sys.stderr)

    if getattr(args, "multi_format", None):
        _req_fmts = []
        for _f in str(args.multi_format).replace("，", ",").split(","):
            _f = _f.strip().lower()
            if not _f:
                continue
            if _f not in ("png", "svg", "pdf", "tiff", "eps"):
                print(f"ERROR: --multi-format 不支持 '{_f}'。可用: png, svg, pdf, tiff, eps",
                      file=sys.stderr)
                sys.exit(1)
            if _f not in _req_fmts:
                _req_fmts.append(_f)
        if not _req_fmts:
            print("ERROR: --multi-format 为空。示例：--multi-format tiff,png,pdf", file=sys.stderr)
            sys.exit(1)
        args.multi_format = _req_fmts
        if args.format:
            print("WARNING: --format 与 --multi-format 同时给出，按 --multi-format 输出",
                  file=sys.stderr)

    if args.batch and args.pipeline:
        print("ERROR: --batch 与 --pipeline 只能二选一（--pipeline 是升级版，支持 YAML 与全局默认）",
              file=sys.stderr)
        sys.exit(1)
    if args.pipeline:
        cmd_pipeline(args.pipeline)
        sys.exit(0)
    if args.batch:
        cmd_batch(args.batch)
        sys.exit(0)

    if args.list_themes:
        cmd_list_themes()
        sys.exit(0)

    if args.theme_swatch:
        resolved = resolve_theme(args.theme_swatch)
        if not resolved:
            print(f"ERROR: 未知主题 '{args.theme_swatch}'。可用: {', '.join(THEME_ORDER)}", file=sys.stderr)
            sys.exit(1)
        out = args.out or (f"theme_{resolved}_swatch.png")
        cmd_theme_swatch(resolved, out)
        sys.exit(0)

    if args.explain:
        cmd_explain(args.explain)
        sys.exit(0)

    if args.suggest:
        if not args.data:
            parser.error("--suggest 需要同时提供 -d/--data")
        cmd_suggest(args.data)
        sys.exit(0)

    if getattr(args, "wizard", False):
        _run_wizard()
        sys.exit(0)

    
    if getattr(args, "pub_ready", False):
        args.verify = True
        if not args.multi_format:
            args.multi_format = ["pdf", "png"]  
        if not args.theme:
            args.theme = "okabe-ito"
        args.pub_ready_applied = True
        print("[pub-ready] 已应用投稿包：--verify（PDF 重叠门禁）+ 色盲安全主题 "
              f"{args.theme} + 多格式导出 {args.multi_format}", file=sys.stderr)

    
    if getattr(args, "quick", False):
        if not args.data:
            parser.error("--quick 需要 -d/--data 指向数据文件（不确定图型可先跑 --suggest）")
        try:
            _qdata = load_data(args.data)
        except Exception as _e:
            print(f"ERROR: cannot load '{args.data}': {_e}", file=sys.stderr)
            sys.exit(1)
        _recs = suggest_chart_type(_qdata)
        _best = _recs[0][1] if _recs else "bar"
        _alt = ", ".join(r[1] for r in _recs[1:3]) if _recs else "—"
        args.type = _best
        if not args.out:
            args.out = "quick_" + _best + ".png"
        print(f"--quick: 已按数据自动选择图型 {_best}（其他候选：{_alt}；"
              "打分明细见 --suggest）", file=sys.stderr)

    if getattr(args, "doctor", False) and not args.out:
        
        if not args.type or not args.data:
            parser.error("--doctor（省略 -o）仍需 -t/--type 与 -d/--data")
        _d = load_data(args.data, chart_type=args.type, sheet=args.sheet)
        _n = _doctor_report(args, _d)
        sys.exit(1 if _n else 0)

    if args.demo:
        if not cmd_demo(args):
            sys.exit(1)
        if not args.type or not args.data or not args.out:
            print("ERROR: --demo 需要 --type/--data/--out", file=sys.stderr)
            sys.exit(1)
    else:
        if not args.type or not args.data or not args.out:
            parser.error("必须提供 -t/--type、-d/--data、-o/--out（或用 --demo 交互模式）")

    if args.style == "glm-hatch":
        args.theme = "glm"
        args.hatch = True

    if args.style == "glm-brand":
        args.theme = "glm-brand"
        args.hatch = True

    if args.style in ("glm-brand", "nature-clean") and args.type == "line" \
            and not args.legend_loc:
        args.direct_label = True  
    if args.style == "nature-clean":
        
        args.theme = "okabe-ito"
        _STYLE_NO_GRID[0] = True
        plt.rcParams.update({
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 1.0,
            "legend.frameon": False,
            "grid.alpha": 0.0,
            "grid.linestyle": "-",
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
        })
        print("[style] nature-clean：Okabe-Ito 配色 + 去顶右框线 + 无网格 + 无框图例"
              "（Nature 系版式语言）", file=sys.stderr)

    if getattr(args, "area", False) and args.type != "venn":
        
        print("[ignored] --area 仅用于 venn；对", args.type,
              "不适用，已忽略（等圆模式为 venn 默认）", file=sys.stderr)
        args.area = False

    if getattr(args, "legend_loc", None):
        _loc = " ".join(args.legend_loc.strip().lower().replace("_", " ")
                        .replace("-", " ").split())
        if _loc not in _LEGEND_LOCS:
            print(f"ERROR: 未知图例位置 '{args.legend_loc}'。可用: best, upper right, "
                  "upper left, lower left, lower right, right, center left, "
                  "center right, lower center, upper center, center", file=sys.stderr)
            sys.exit(1)
        args.legend_loc = _loc
    try:
        annotations = _parse_annotations(args.annotate)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    theme_key = resolve_theme(args.theme)
    if not theme_key:
        print(f"ERROR: 未知主题 '{args.theme}'。运行 --list-themes 查看全部配色。", file=sys.stderr)
        sys.exit(1)
    if args.journal and args.theme is None and args.journal in JOURNAL_THEME:
        
        theme_key = JOURNAL_THEME[args.journal]
        print(f"配色已联动 {theme_key} 主题（显式 --theme 可覆盖）", file=sys.stderr)
    args.theme = theme_key
    theme = THEMES[theme_key]

    
    if args.journal and getattr(args, "width", None):
        print("[auto] --journal 锁定图宽，--width "
              f"{args.width} 已被忽略（--height 仍生效）", file=sys.stderr)
    if (args.type in ("bar", "grouped_bar") and args.data
            and str(args.data).lower().endswith(".csv")):
        print("[hint] CSV 不支持误差棒——需要误差棒/显著性标记请改用 JSON 格式"
              "（errors/significance 字段，见 --explain bar）", file=sys.stderr)
        print("[auto] --journal 锁定图宽，--width "
              f"{args.width} 已被忽略（--height 仍生效）", file=sys.stderr)
    if getattr(args, "verify", False):
        _fmt = os.path.splitext(str(args.out or ""))[1].lower()
        if _fmt and _fmt != ".pdf":
            print("[auto] --verify 仅对 PDF 输出生效；当前输出为 "
                  f"{_fmt or '无扩展名'}，本次不做像素级重叠检查", file=sys.stderr)
    if args.journal:
        preset = JOURNAL_PRESETS[args.journal]
        if preset.get("cjk_default"):
            args.cjk = True  
        theme = dict(theme)
        w_in = preset["widths_mm"][args.column] / 25.4
        h_ratio = theme["figsize"][1] / theme["figsize"][0]
        theme["figsize"] = (w_in, w_in * h_ratio)
        theme["font_size"] = preset["font_size"]
        theme["dpi"] = preset["dpi"]
        if preset["font_family"] not in plt.rcParams['font.sans-serif']:
            plt.rcParams['font.sans-serif'].insert(0, preset["font_family"])
        print(f"期刊预设 {args.journal}（{args.column} 栏，宽 {w_in:.2f}in，"
              f"字体 {preset['font_family']} {preset['font_size']}pt，最小字号 {preset['min_text_size']}pt"
              f"— 可用 audit_pdf.py --min-size {preset['min_text_size']} 核查）", file=sys.stderr)
    if getattr(args, "size", None):
        rw, rh = (float(v) for v in args.size.split(":"))
        w_in, h_in = theme["figsize"]
        theme["figsize"] = (w_in, w_in * rh / rw)
        print(f"画幅预设 {args.size}：figsize {w_in:.2f}x{theme['figsize'][1]:.2f}in"
              f"（宽度不变，高度按比例）", file=sys.stderr)
    if args.stats == "cox":
        if args.type != "forest":
            print("ERROR: --stats cox 仅支持 forest 图型（原始生存数据→多因素 Cox→HR 森林图）。"
                  "其他图型的 --stats 请用 auto/multi。", file=sys.stderr)
            sys.exit(1)
        data = _run_cox_forest(args)
    else:
        data = load_data(args.data, chart_type=args.type, sheet=args.sheet)

    
    
    
    if (args.type == "cluster_heatmap" and isinstance(data, dict)
            and isinstance(data.get("matrix"), list)):
        _m = data["matrix"]
        _n = len(_m)
        _ds = getattr(args, "downsample", None)
        if _n > 3000 and not _ds:
            _ds = 2000
            print(f"AUTO-DOWNSAMPLE: cluster_heatmap 行数 {_n} 超过硬上限 3000——"
                  "已自动等距采样到 2000 行（确定性采样；需要其他行数用 --downsample N）",
                  file=sys.stderr)
        if _ds and _n > _ds:
            _step = -(-_n // max(int(_ds), 1))
            _idx = list(range(0, _n, _step))
            data["matrix"] = [_m[i] for i in _idx]
            for _k in ("row_labels", "rows", "y_labels"):
                if isinstance(data.get(_k), list) and len(data[_k]) == _n:
                    data[_k] = [data[_k][i] for i in _idx]
            print(f"downsample: cluster_heatmap 行数 {_n} → {len(data['matrix'])}"
                  f"（等距采样，步长 {_step}）", file=sys.stderr)

    
    for _adv in _preflight_advisories(data, args.type,
                                      getattr(args, "downsample", None)):
        print(f"WARNING: {_adv}", file=sys.stderr)

    
    _ignored = []
    if args.stats in ("auto", "multi", "bootstrap") and args.type not in ("box", "violin"):
        _ignored.append(f"--stats {args.stats}（仅 box/violin 生效）")
    if args.compare and args.type != "roc":
        _ignored.append("--compare（仅 roc 生效）")
    if args.egger and args.type != "funnel":
        _ignored.append("--egger（仅 funnel 生效）")
    if args.hatch and args.type not in ("bar", "grouped_bar", "hbar", "horizontal_bar", "stacked_bar"):
        _ignored.append("--hatch（仅 bar 系生效）")
    if args.area and args.type != "venn":
        _ignored.append("--area（仅 venn 生效）")
    if args.sheet and not str(args.data or "").lower().endswith((".xlsx", ".xls")):
        _ignored.append("--sheet（仅 .xlsx 生效）")
    if getattr(args, "order", None) and args.type not in _ORDER_CHARTS:
        _ignored.append("--order（仅 bar/box/violin/line 系生效）")
        args.order = None
    if getattr(args, "normalize", None) and args.type not in _NORM_CHARTS:
        _ignored.append("--normalize（仅 bar 系/line 生效；分布数据不做均值归一）")
        args.normalize = None
    for _ig in _ignored:
        print(f"[ignored] {_ig} 对 {args.type} 不适用，本次渲染已忽略", file=sys.stderr)

    
    for _w in _field_nearmiss_warnings(data):
        print(f"WARNING: {_w}", file=sys.stderr)

    fatal_msgs, warn_msgs = validate_data(data, args.type)
    for w in warn_msgs:
        print(f"WARNING: {w}", file=sys.stderr)
    if fatal_msgs:
        for m in fatal_msgs:
            print(f"ERROR: {m}", file=sys.stderr)
        if any("CSV" in m or "csv" in m for m in fatal_msgs) or \
           any("error" in m.lower() and "bar" in m.lower() for m in fatal_msgs):
            print("HINT: CSV 不支持误差棒 → 改用 JSON 格式（见 --explain bar / 文档 §数据输入）",
                  file=sys.stderr)
        sys.exit(1)
    _memory_hint(data, args.type)
    
    if getattr(args, "order", None):
        try:
            apply_series_order(data, args.order, args.type)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    if getattr(args, "normalize", None):
        try:
            apply_normalize(data, args.normalize, args.type)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    if getattr(args, "doctor", False):
        _doctor_report(args, data)
    
    if args.timeout is None or args.timeout > 0:
        _watchdog_arm(args.type, data,
                      budget=None if args.timeout is None else float(args.timeout))
    cjk_fp = None
    
    def _scan_cjk(obj):
        if isinstance(obj, str):
            return has_cjk(obj)
        if isinstance(obj, dict):
            return any(_scan_cjk(k) for k in obj.keys()) or any(_scan_cjk(v) for v in obj.values())
        if isinstance(obj, (list, tuple)):
            return any(_scan_cjk(v) for v in obj)
        return False

    def _text_has_cjk():
        for t in [args.title, args.xlabel, args.ylabel]:
            if t and has_cjk(t):
                return True
        
        return _scan_cjk(data) if data else False
    _auto_cjk = _text_has_cjk()
    if args.cjk or args.cjk_font or _auto_cjk:
        cjk_fp, cjk_name = load_cjk_font(args.cjk_font)
        if cjk_name:
            plt.rcParams['font.sans-serif'] = [cjk_name, 'DejaVu Sans'] + plt.rcParams['font.sans-serif']
        plt.rcParams['axes.unicode_minus'] = False
        if cjk_fp:
            print(f"已加载中文字体: {cjk_name}", file=sys.stderr)
        else:
            print("WARNING: 未找到中文字体，中文可能显示为方框", file=sys.stderr)

    
    width = args.width if args.width else theme["figsize"][0]
    height = args.height if args.height else theme["figsize"][1]
    km_risk = False
    risk_axes = None
    if args.type in ("km", "survival") and not getattr(args, "no_risk_table", False):
        _g = data.get("groups", data.get("series")) if isinstance(data, dict) else None
        if isinstance(_g, dict) and _g:
            def _is_raw_km(v):
                if not isinstance(v, (list, tuple)) or len(v) == 0:
                    return False
                if isinstance(v[0], (list, tuple)):
                    if not all(isinstance(p, (list, tuple)) and len(p) >= 2 for p in v[:8]):
                        return False
                    try:
                        seconds = [float(p[1]) for p in v[:8]]
                    except (TypeError, ValueError):
                        return False
                    return all(s in (0.0, 1.0) for s in seconds)
                return all(isinstance(x, (int, float)) for x in v[:5])
            try:
                km_risk = all(_is_raw_km(v) for v in _g.values())
            except Exception:
                km_risk = False
    if args.type == "cluster_heatmap" and isinstance(data, dict):
        _ch_rows = len(data.get("matrix", data.get("data", data.get("values"))) or [])
        height = max(height, min(_ch_rows * 0.16 + 1.0, 24.0))
    if args.type == "pca" and isinstance(data, dict):
        _pca_n = len(data.get("matrix") or [])
        _has_groups = bool(data.get("groups"))
        if not _has_groups and 0 < _pca_n:
            width = max(width, 8.5)
            height = max(height, 6.0)
    def _make_fig():

        if km_risk:
            _n_rows = len(data.get("groups", data.get("series", {})) or {})
            _rt_h = min(0.9, 0.34 + 0.24 * max(_n_rows, 1))
            _f, _axes = plt.subplots(
                2, 1, figsize=(width, height + _rt_h),
                gridspec_kw={"height_ratios": [3.4, _rt_h]})
            return _f, _axes[0], _axes[1]
        _f, _a = plt.subplots(figsize=(width, height))
        return _f, _a, None

    fig, ax, risk_axes = _make_fig()

    
    gen_func = GENERATORS[args.type]
    kwargs = {
        "show_values": args.show_values,
        "trend": args.trend and not args.no_trend,
        "peak_label": getattr(args, "peak_label", False),
        "cmap": args.cmap,
        "vmin": args.vmin,
        "vmax": args.vmax,
        "horizontal": args.horizontal or args.type in ("hbar", "horizontal_bar"),
        "hatch": args.hatch,
        "direct_label": getattr(args, "direct_label", False),
        "alternate": args.alternate,
        "show_ratio": args.show_ratio,
        "ratio_base": args.ratio_base,
        "stats_auto": args.stats == "auto",
        "stats_bootstrap": args.stats == "bootstrap",
        "stats_multi": args.stats == "multi",
        "roc_compare": getattr(args, "compare", False),
        "sensitivity": getattr(args, "sensitivity", False),
        "median_auto": not getattr(args, "no_median", False),
        "egger": getattr(args, "egger", False),
        "area_mode": getattr(args, "area", False),
        "risk_table": km_risk,
        "risk_axes": risk_axes if km_risk else None,
        "risk_times": getattr(args, "risk_times", None),
        "auto_cjk_hdr": bool(args.cjk) and args.type in ("km", "survival"),
    }
    _a2_degraded = False
    for _a2_try in (1, 2):
        try:
            extra = gen_func(data, ax, theme, cjk_fp, **kwargs)
            break
        except MemoryError:
            plt.close(fig)
            if _a2_try == 2:
                raise
            width, height = width * 0.85, height * 0.85
            fig, ax, risk_axes = _make_fig()
            kwargs["risk_axes"] = risk_axes if km_risk else None
            _a2_degraded = True
            print("WARNING: 渲染内存不足——已自动降级重试（图幅 ×0.85，输出 DPI 减半）",
                  file=sys.stderr)

    
    is_self_managed = extra in ("composite", "diagram")

    
    if args.type not in ('dual_axis',) and not is_self_managed:
        apply_base_style(ax, theme)

    
    if not is_self_managed:
        if args.title:
            title_text = args.title.replace('\\n', '\n')
            _t_pad = 22 if getattr(args, "subtitle", None) else 12
            ax.set_title(title_text, fontsize=theme["font_size"] + 1, fontweight='bold',
                         pad=_t_pad,
                         fontproperties=cjk_fp if cjk_fp and has_cjk(title_text) else None)
        if getattr(args, "summary", False) and not getattr(args, "subtitle", None):
            
            
            try:
                _sum_txt = _auto_summary(data, args.type)
            except Exception:
                _sum_txt = None
            if _sum_txt:
                print(f"summary: {_sum_txt}", file=sys.stderr)
            args.subtitle = _sum_txt
        if getattr(args, "subtitle", None):
            
            _sub = str(args.subtitle).strip()[:200]
            ax.text(0.5, 1.012, _sub, transform=ax.transAxes, ha="center", va="bottom",
                    fontsize=theme["font_size"] - 1, color="#555555",
                    fontproperties=cjk_fp if cjk_fp and has_cjk(_sub) else None)
        if getattr(args, "source", None):
            
            
            _src = str(args.source).strip()[:200]
            try:
                fig.supxlabel(_src, x=0.995, ha="right",
                              fontsize=max(5.5, theme["font_size"] - 2), color="#777777",
                              fontproperties=cjk_fp if cjk_fp and has_cjk(_src) else None)
            except AttributeError:  
                fig.text(0.995, 0.005, _src, ha="right", va="bottom",
                         fontsize=max(5.5, theme["font_size"] - 2), color="#777777",
                         fontproperties=cjk_fp if cjk_fp and has_cjk(_src) else None)
        if args.xlabel:
            ax.set_xlabel(args.xlabel, fontsize=theme["font_size"],
                          fontproperties=cjk_fp if cjk_fp and has_cjk(args.xlabel) else None)
        if args.ylabel:
            ax.set_ylabel(args.ylabel, fontsize=theme["font_size"],
                          fontproperties=cjk_fp if cjk_fp and has_cjk(args.ylabel) else None)
            _ensure_ylabel_clear(ax)

        
        if extra is not None and hasattr(extra, 'get_cmap'):
            cbar = fig.colorbar(extra, ax=ax, shrink=0.8)
            cbar_label = data.get("cbar_label", args.ylabel)
            if cbar_label:
                cbar.set_label(cbar_label, fontsize=theme["font_size"] - 1,
                              fontproperties=cjk_fp if cjk_fp and has_cjk(cbar_label) else None)

        
        _dl = getattr(args, "direct_label", False) and args.type == "line"
        
        
        if not _dl and args.type != "dual_axis" and not args.no_legend \
                and args.legend and ax.get_legend_handles_labels()[1]:
            ax.legend(fontsize=theme["font_size"] - 1, loc='best', framealpha=0.9,
                      prop=cjk_fp if cjk_fp else None)
        if args.type in ("bar", "grouped_bar", "hbar", "horizontal_bar", "line", "stacked_bar"):
            n_series = len(data.get("series", data.get("datasets", {})))
        elif args.type == "scatter":
            groups = data.get("groups")
            n_series = len(set(groups)) if isinstance(groups, (list, tuple)) and groups else 1
        else:
            n_series = 1
        audit_msg = legend_audit(ax, args.type, args.no_legend, n_series)
        if audit_msg:
            print(f"WARNING: {audit_msg}", file=sys.stderr)

    
    
    if annotations:
        cjk_fp = _apply_annotations(fig, annotations, theme, cjk_fp)
    if getattr(args, "legend_loc", None) or getattr(args, "legend_outside", False):
        _apply_legend_control(fig, loc=args.legend_loc, outside=args.legend_outside,
                              theme=theme, cjk_fp=cjk_fp)

    
    
    
    import matplotlib.text as _mtext
    _cjk_texts = [t for t in fig.findobj(_mtext.Text)
                  if t.get_text() and has_cjk(t.get_text())]
    if _cjk_texts:
        if cjk_fp is None:
            try:
                cjk_fp, cjk_name = load_cjk_font(None)
                if cjk_fp:
                    plt.rcParams['font.sans-serif'] = [cjk_name, 'DejaVu Sans']
                    plt.rcParams['axes.unicode_minus'] = False
                    print(f"自动补启用中文字体: {cjk_name}（图内含自动生成的中文标注）",
                          file=sys.stderr)
            except Exception:
                pass
        if cjk_fp is not None:
            _fixed = 0
            for _t in _cjk_texts:
                try:
                    _t.set_fontproperties(cjk_fp)
                    _fixed += 1
                except Exception:
                    pass
            if _fixed:
                print(f"CJK 字体兜底：{_fixed} 处含中文文本已统一挂中文字体", file=sys.stderr)

    if not is_self_managed:
        plt.tight_layout()

    
    
    fix_tick_overlaps(fig)

    
    out_ext = os.path.splitext(args.out)[1].lower()
    fmt_map = {'.png': 'png', '.svg': 'svg', '.pdf': 'pdf', '.tiff': 'tiff', '.tif': 'tiff', '.eps': 'eps'}
    if getattr(args, "multi_format", None):
        _base = os.path.splitext(args.out)[0]
        save_targets = [(fmt, _base + "." + fmt) for fmt in args.multi_format]
    else:
        out_format = args.format if args.format else fmt_map.get(out_ext, 'png')
        _is_vec = out_format in ('svg', 'pdf', 'eps')
        final_out = args.out
        if not _is_vec and out_ext not in fmt_map:
            final_out = args.out + '.' + out_format
        save_targets = [(out_format, final_out)]

    
    
    dpi = args.dpi if args.dpi else theme["dpi"]
    if _a2_degraded:
        dpi = max(150, int(dpi) // 2)

    saved_files = []
    for out_format, final_out in save_targets:
        is_vector = out_format in ('svg', 'pdf', 'eps')
        
        save_kwargs = {
            "dpi": dpi,
            "bbox_inches": 'tight',
            "facecolor": 'white',
            "edgecolor": 'none',
        }
        if out_format == 'tiff':
            save_kwargs["pil_kwargs"] = {"compression": "tiff_lzw"}
        for _attempt in (1, 2):
            try:
                fig.savefig(final_out, format=out_format, **save_kwargs)
                break
            except OSError as e:
                if _attempt == 1:
                    print(f"WARNING: 文件写出失败（{e}），0.5 秒后自动重试一次…", file=sys.stderr)
                    time.sleep(0.5)
                else:
                    raise
            except MemoryError:
                if _attempt == 1:
                    save_kwargs["dpi"] = max(150, int(save_kwargs["dpi"]) // 2)
                    print("WARNING: 输出内存不足——DPI 已降为 "
                          f"{save_kwargs['dpi']} 自动重试一次…", file=sys.stderr)
                else:
                    raise
        saved_files.append((out_format, final_out, is_vector))
    plt.close()

    if args.alt:
        try:
            alt = generate_alt_text(args.type, data, args.title)
            alt_path = os.path.splitext(final_out)[0] + ".alt.txt"
            with open(alt_path, "w", encoding="utf-8") as f:
                f.write(alt + "\n")
            print(f"无障碍描述: {alt_path}", file=sys.stderr)
        except Exception as e:  
            print(f"WARNING: alt text generation failed: {e}", file=sys.stderr)

    if getattr(args, "caption", False):
        try:
            if _afcharts is not None:
                cap = _afcharts.make_caption(args.type, data, args.title)
            else:
                cap = args.title or args.type
            cap_path = os.path.splitext(final_out)[0] + ".caption.txt"
            with open(cap_path, "w", encoding="utf-8") as f:
                f.write(cap + "\n")
            print(f"图注: {cap_path}", file=sys.stderr)
        except Exception as e:  
            print(f"WARNING: caption generation failed: {e}", file=sys.stderr)

    cjk_info = " (colorblind-safe)" if theme.get("colorblind_safe") else ""
    if len(saved_files) == 1:
        out_format, final_out, is_vector = saved_files[0]
        sz = os.path.getsize(final_out)
        fmt_info = f"{out_format.upper()} @ {dpi}DPI" if not is_vector else f"{out_format.upper()} 矢量"
        print(f"已保存: {final_out}（{sz:,} 字节，{fmt_info}{cjk_info}）", file=sys.stderr)
    else:
        for _fmt, _path, _isvec in saved_files:
            sz = os.path.getsize(_path)
            fmt_info = f"{_fmt.upper()} @ {dpi}DPI" if not _isvec else f"{_fmt.upper()} 矢量"
            print(f"已保存: {_path}（{sz:,} 字节，{fmt_info}{cjk_info}）", file=sys.stderr)

    if getattr(args, "multi_format", None):
        _pdf_pick = [_p for _f, _p, _ in saved_files if _f == "pdf"]
        if _pdf_pick:
            out_format, final_out, is_vector = "pdf", _pdf_pick[0], True
        else:
            print("WARNING: --verify 只核查 PDF；--multi-format 中没有 PDF，跳过核查",
                  file=sys.stderr)
            args.verify = False
    if args.verify:
        if out_format != 'pdf':
            print("WARNING: --verify only applies to PDF output; skipping", file=sys.stderr)
        else:
            try:
                sys.path.insert(0, SCRIPT_DIR)
                from verify_overlap_pixel import verify
            except ImportError:
                print("WARNING: --verify requires PyMuPDF (fitz) and scipy — install with: pip install pymupdf scipy",
                      file=sys.stderr)
            else:
                real_overlaps, details = verify(final_out)
                if real_overlaps > 0:
                    print(f"VERIFY FAIL: {real_overlaps} real text overlap(s) in {final_out} — exit code 2",
                          file=sys.stderr)
                    sys.exit(2)
                print(f"VERIFY OK: no text overlaps in {final_out}", file=sys.stderr)






_WD_BASE_BUDGET = {
    "cluster_heatmap": 240, "composite": 180, "pca": 120, "km": 120,
    "forest": 90, "venn": 90, "prisma": 60,
}
_WD_DEFAULT_BUDGET = 90.0
_WD_MIN, _WD_MAX = 30.0, 1800.0


def _wd_estimate_rows(data):

    try:
        if not isinstance(data, dict):
            return 0
        m = data.get("matrix")
        if isinstance(m, list) and m:
            return len(m)
        g = data.get("groups")
        if isinstance(g, dict) and g:
            return max(len(v) for v in g.values())
        s = data.get("series")
        if isinstance(s, dict) and s:
            return max(len(v) for v in s.values())
        x = data.get("x")
        if isinstance(x, list):
            return len(x)
    except Exception:
        pass
    return 0


def _wd_budget_for(chart_type, data):
    rows = _wd_estimate_rows(data)
    base = _WD_BASE_BUDGET.get(chart_type, _WD_DEFAULT_BUDGET)
    factor = 1.0 + min(3.0, rows / 2000.0)
    return max(_WD_MIN, min(_WD_MAX, base * factor))


def _watchdog_arm(chart_type, data, budget=None):



    if os.environ.get("AF_NO_WATCHDOG"):
        return None
    if budget is None:
        budget = _wd_budget_for(chart_type, data)
    start = time.time()
    main_t = threading.main_thread()

    def _fire():
        el = time.time() - start
        print("ERROR: 渲染看门狗超时——图表未能按时完成，已强制中断（exit 5）",
              file=sys.stderr)
        print(f"└ 已用时 {el:.0f}s，超过预算 {budget:.0f}s"
              f"（图型={chart_type}，数据规模≈{_wd_estimate_rows(data)} 行）",
              file=sys.stderr)
        print("建议1: 数据过大先瘦身——cluster_heatmap 可加 --downsample 2000 等距采样",
              file=sys.stderr)
        print("建议2: 调大预算 --timeout 600；或本图禁用看门狗 --timeout 0",
              file=sys.stderr)
        print("建议3: composite 面板过多时拆成多图分别渲染", file=sys.stderr)
        os._exit(5)

    def _monitor():
        warned = set()
        while True:
            time.sleep(1.0)
            if not main_t.is_alive():
                return
            el = time.time() - start
            if el >= budget:
                _fire()
                return
            for frac, tag in ((0.5, "50%"), (0.8, "80%")):
                if el >= budget * frac and tag not in warned:
                    warned.add(tag)
                    print(f"WARNING: 渲染已用时 {el:.0f}s（预算 {budget:.0f}s 的 {tag}）——"
                          f"超时将中断并给出建议", file=sys.stderr)

    t = threading.Thread(target=_monitor, name="af-watchdog", daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        sys.exit(130)
    except SystemExit:
        raise
    except (ValueError, KeyError, FileNotFoundError, json.JSONDecodeError) as e:
        if os.environ.get("AF_DEBUG"):
            raise
        _print_v3_error(e)
        sys.exit(_classify_exit_code(e))
    except Exception as e:  
        if os.environ.get("AF_DEBUG"):
            raise  
        _print_v3_error(e)
        sys.exit(_classify_exit_code(e))
