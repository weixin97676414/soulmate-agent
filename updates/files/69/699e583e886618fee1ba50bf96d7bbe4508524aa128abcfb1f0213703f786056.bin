# -*- coding: utf-8 -*-
"""af_draw — 核心图型生成器+统计标注助手（v4.0.0 模块化第四刀，自 gen_figure 拆出）。

拆分后 gen_figure 主文件保留：参数解析/校验/统计推断/流水线/文档；
本模块只做绘制。公开名经 gen_figure 再导出，`import gen_figure` 用法不变。
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

try:
    import af_v23_stats as _afstats
except ImportError:  # 统计模块不在同目录时降级（标注函数自行判 None 提示）
    _afstats = None
from af_shared import has_cjk, HATCH_PATTERNS, _STYLE_NO_GRID, _ensure_ylabel_clear


def _darken_color(color, factor=0.55):
    """Return a darker shade of the given color. (Legacy; hatch now uses black.)"""
    import matplotlib.colors as mcolors
    try:
        rgb = mcolors.to_rgb(color)
        return tuple(c * factor for c in rgb)
    except Exception:
        return (0.2, 0.2, 0.2)


# ── Auto significance annotations (v2.2) ──────────────────────────────

def _sig_stars(p):
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "NS"


def pairwise_vs_first(series):
    """Compare each series against the first one: Shapiro normality test,
    then Welch t-test (both normal) or Mann-Whitney U (otherwise).
    Returns [(name, p_or_None, stars, method)]. Requires scipy."""
    from scipy import stats as _st
    names = list(series.keys())
    if len(names) < 2:
        return []
    ref_all = np.asarray(series[names[0]], dtype=float)
    ref_all = ref_all[np.isfinite(ref_all)]
    out = []
    for name in names[1:]:
        vals = np.asarray(series[name], dtype=float)
        vals = vals[np.isfinite(vals)]
        if len(vals) < 3 or len(ref_all) < 3:
            out.append((name, None, "n.s.", "n<3"))
            continue
        normal = True
        for arr in (ref_all, vals):
            if 3 <= len(arr) <= 5000:
                _, sp = _st.shapiro(arr)
                if sp <= 0.05:
                    normal = False
                    break
        if normal:
            _, p = _st.ttest_ind(ref_all, vals, equal_var=False)
            method = "Welch t"
        else:
            _, p = _st.mannwhitneyu(ref_all, vals, alternative="two-sided")
            method = "Mann-Whitney U"
        out.append((name, float(p), _sig_stars(float(p)), method))
    return out


def draw_bootstrap_brackets(ax, positions, results, data_top, font_size=8):
    """v3.5：bootstrap 均值差 95%CI 括号（文本=Δ 与 CI 区间，非 p 星号）。"""
    span = max(abs(data_top) * 0.08, 1e-9)
    for j, (name, diff, lo, hi) in enumerate(results):
        if diff is None:
            continue
        yi = data_top + span * (0.55 + 1.05 * j)
        x0, x1 = positions[0], positions[j + 1]
        ax.plot([x0, x0, x1, x1],
                [yi - span * 0.22, yi, yi, yi - span * 0.22],
                color="#333333", lw=1.2, zorder=6)
        sig = "" if (lo > 0 or hi < 0) else "（CI 含 0）"
        ax.text((x0 + x1) / 2, yi + span * 0.10,
                f"Δ={diff:.3g}, 95%CI[{lo:.3g},{hi:.3g}]{sig}",
                ha="center", va="bottom", fontsize=font_size, color="#333333", zorder=6)
    return data_top + span * (0.55 + 1.05 * max(0, len(results) - 1)) + span * 0.6


def annotate_bootstrap_stats(ax, series, positions, theme, chart_type):
    """--stats bootstrap 入口（box/violin）：每组均值 bootstrap CI 误差棒
    + 组间均值差 CI 括号 + stderr 报告（确定性：固定种子）。"""
    names = list(series.keys())
    if len(names) < 2:
        print(f"WARNING: --stats bootstrap needs >= 2 series ({chart_type}); skipped",
              file=sys.stderr)
        return
    import os as _os
    seed = int(_os.environ.get("AF_BOOTSTRAP_SEED", "20260925"))
    try:
        from af_v23_stats import bootstrap_ci, bootstrap_vs_first, bootstrap_median_ci
        per_group = [(n,) + bootstrap_ci(v, seed=seed) for n, v in series.items()]
        med_ci = [(n,) + bootstrap_median_ci(v, seed=seed) for n, v in series.items()]
        diffs = bootstrap_vs_first(series, seed=seed)
    except ImportError:
        print("WARNING: --stats bootstrap requires numpy（环境侧，退出码 4）", file=sys.stderr)
        return
    except ValueError as e:
        print(f"WARNING: --stats bootstrap: {e}", file=sys.stderr)
        return
    # 每组均值 ± bootstrap CI 误差棒（画在组位置上）
    for (name, stat, lo, hi), x_pos in zip(per_group, positions):
        err_lo, err_hi = stat - lo, hi - stat
        ax.errorbar(x_pos, stat, yerr=[[max(err_lo, 0)], [max(err_hi, 0)]],
                    fmt="D", markersize=4, color="#333333", ecolor="#333333",
                    elinewidth=1.4, capsize=4, capthick=1.4, zorder=7)
    data_top = max(max([float(v) for v in vals]) for vals in series.values() if len(vals))
    top = draw_bootstrap_brackets(ax, positions, diffs, data_top,
                                  font_size=max(6, theme["font_size"]))
    lo_ax, hi_ax = ax.get_ylim()
    if top > hi_ax:
        ax.set_ylim(lo_ax, top)
    print(f"stats bootstrap（percentile 法，{5000} 次重采样，种子 {seed}）：", file=sys.stderr)
    for name, stat, lo, hi in per_group:
        print(f"  {name}: 均值={stat:.4g}, 95%CI[{lo:.4g},{hi:.4g}]", file=sys.stderr)
    for (name, med, mlo, mhi), (_, stat, lo, hi) in zip(med_ci, per_group):
        print(f"  {name}: 中位数={med:.4g}, 95%CI[{mlo:.4g},{mhi:.4g}]"
              f"（偏态数据建议引用中位数 CI 而非均值 CI）", file=sys.stderr)
    g0 = names[0]
    for name, diff, lo, hi in diffs:
        if diff is None:
            continue
        verdict = "稳健差异" if (lo > 0 or hi < 0) else "CI 含 0（不能断言差异）"
        print(f"  {g0} vs {name}: 均值差 Δ={diff:.4g}, 95%CI[{lo:.4g},{hi:.4g}] —— {verdict}",
              file=sys.stderr)


def draw_stat_brackets(ax, positions, results, data_top, font_size=8):
    """Draw one comparison bracket per result (each group vs group 0), stacked
    above the tallest data point. Returns the new suggested ylim top."""
    span = max(abs(data_top) * 0.08, 1e-9)
    for j, (name, p, stars, method) in enumerate(results):
        if p is None:
            continue
        yi = data_top + span * (0.55 + 1.05 * j)
        x0, x1 = positions[0], positions[j + 1]
        ax.plot([x0, x0, x1, x1],
                [yi - span * 0.22, yi, yi, yi - span * 0.22],
                color="#333333", lw=1.2, zorder=6)
        ax.text((x0 + x1) / 2, yi + span * 0.10, stars, ha="center",
                va="bottom", fontsize=font_size, color="#333333", zorder=6)
    return data_top + span * (0.55 + 1.05 * max(0, len(results) - 1)) + span * 0.6


def annotate_auto_stats(ax, series, positions, theme, chart_type):
    """--stats auto entry point for box/violin: compute + draw + report."""
    names = list(series.keys())
    if len(names) < 2:
        print(f"WARNING: --stats auto needs >= 2 series ({chart_type}); skipped",
              file=sys.stderr)
        return
    try:
        results = pairwise_vs_first(series)
    except ImportError:
        print("WARNING: --stats auto requires scipy — install with: pip install scipy",
              file=sys.stderr)
        return
    data_top = max(max([float(v) for v in vals]) for vals in series.values() if len(vals))
    top = draw_stat_brackets(ax, positions, results, data_top,
                             font_size=max(6, theme["font_size"]))
    lo, hi = ax.get_ylim()
    if top > hi:
        ax.set_ylim(lo, top)
    g0 = names[0]
    for name, p, stars, method in results:
        p_txt = "NA" if p is None else f"{p:.4g}"
        print(f"  stats ({chart_type}): {g0} vs {name}: {method}, p={p_txt} -> {stars}",
              file=sys.stderr)


def annotate_multi_stats(ax, series, positions, theme, chart_type):
    """--stats multi 入口：全两两比较（正态→Tukey；否则 Kruskal-Wallis+Dunn+Hochberg）。"""
    if _afstats is None:
        print("WARNING: --stats multi 需要 af_v23_stats.py 与 gen_figure.py 同目录",
              file=sys.stderr)
        return
    names = list(series.keys())
    if len(names) < 3:
        print("WARNING: --stats multi 需要 >=3 组（两组比较请用 --stats auto）",
              file=sys.stderr)
        return
    clean = {}
    for n, v in series.items():
        arr = np.asarray(v, dtype=float)
        clean[n] = arr[np.isfinite(arr)]
    try:
        pairs = _afstats.multi_pairwise(clean)
    except ValueError as e:
        print(f"WARNING: --stats multi 无法计算：{e}", file=sys.stderr)
        return
    data_top = max(max([float(x) for x in v]) for v in clean.values() if len(v))
    span = max(abs(data_top) * 0.08, 1e-9)
    sig = [t for t in pairs if t[2] is not None]
    if len(sig) > 8:
        print(f"WARNING: 显著对比 {len(sig)} 对，仅绘制前 8 对括号（完整结果见 stderr 报告）",
              file=sys.stderr)
    top_needed = data_top
    for idx, (a_name, b_name, p, stars, method) in enumerate(sig[:8]):
        yi = data_top + span * (0.55 + 1.05 * idx)
        x0 = positions[names.index(a_name)]
        x1 = positions[names.index(b_name)]
        ax.plot([x0, x0, x1, x1],
                [yi - span * 0.22, yi, yi, yi - span * 0.22],
                color="#333333", lw=1.2, zorder=6)
        ax.text((x0 + x1) / 2, yi + span * 0.10, stars, ha="center",
                va="bottom", fontsize=max(6, theme["font_size"]), color="#333333", zorder=6)
        top_needed = yi + span * 0.6
    lo, hi = ax.get_ylim()
    if top_needed > hi:
        ax.set_ylim(lo, top_needed)
    for a_name, b_name, p, stars, method in pairs:
        print(f"  stats ({chart_type}): {a_name} vs {b_name}: {method}, p={p:.4g} -> {stars}",
              file=sys.stderr)


# ── Alt text generation (v2.2, accessibility) ─────────────────────────


def _hatch_edgecolor(theme, fill_color):
    """斜纹描边色：主题声明 hatch_edge=auto 时用填充同系深色，否则黑色（历史行为）。"""
    if not isinstance(theme, dict) or theme.get("hatch_edge") != "auto":
        return "black"
    fills = fill_color if isinstance(fill_color, list) else [fill_color]
    return [_darken_color(c, 0.55) for c in fills] if isinstance(fill_color, list) \
        else _darken_color(fill_color, 0.55)


def apply_base_style(ax, theme):
    """Apply common styling to axes."""
    for spine in theme["spines"]:
        ax.spines[spine].set_visible(False)
    if _STYLE_NO_GRID[0]:
        ax.grid(False)
        ax.tick_params(labelsize=theme["font_size"] - 1, length=3, width=1.0)
        return
    ax.yaxis.grid(True, alpha=theme["grid_alpha"], linestyle='--')
    ax.tick_params(labelsize=theme["font_size"] - 1)


def gen_bar(data, ax, theme, cjk_fp, **kwargs):
    """Grouped bar chart with horizontal mode, hatching, error bars, significance, and ratio annotations."""
    labels = data.get("labels", data.get("x", []))
    series = data.get("series", data.get("datasets", {}))

    n_groups = len(labels)
    n_series = len(series)
    x = np.arange(n_groups)
    w = 0.8 / max(n_series, 1)
    colors = theme["colors"]
    horizontal = kwargs.get("horizontal", False)
    use_hatch = kwargs.get("hatch", False)
    show_ratio = kwargs.get("show_ratio", False)
    ratio_base = kwargs.get("ratio_base", 0)  # index of base series for ratio

    error_data = data.get("errors", {})
    significance = data.get("significance", {})

    bar_func = ax.barh if horizontal else ax.bar
    all_bars = []  # store for ratio calculation

    for i, (name, values) in enumerate(series.items()):
        offset = (i - (n_series - 1) / 2) * w
        errs = None
        if name in error_data and error_data[name]:
            errs = error_data[name]
            if isinstance(errs, list) and all(isinstance(e, (int, float)) for e in errs):
                pass  # per-bar error
            elif isinstance(errs, (int, float)):
                errs = [errs] * n_groups

        hatch_val = HATCH_PATTERNS[i % len(HATCH_PATTERNS)] if use_hatch else None
        # v3.10 单系列视觉增强（真金链路反馈"默认出图朴素"）：
        # ①Top-N 强调层级——最大条(含并列)主题主色，其余同色淡化（focus+context）
        # ②斜纹豁免——斜纹是"系列区分"工具，单系列铺满=噪声
        # ③图例抑制——单系列图例=系列名复读（label 不设，图例自然消失）
        _single_enh = (n_series == 1 and len(values) >= 3
                       and not kwargs.get("alternate", False))
        if kwargs.get("alternate", False) and n_series == 1:
            # GLM-5.2 blog style: alternate first two theme colors per bar
            bar_colors = [colors[j % 2] for j in range(len(values))]
        elif _single_enh:
            from matplotlib.colors import to_rgba
            _vals = [float(v) for v in values]
            _vmax = max(_vals)
            _accent = colors[i % len(colors)]
            _muted = to_rgba(_accent, 0.42)
            bar_colors = [_accent if abs(v - _vmax) < 1e-12 else _muted for v in _vals]
            hatch_val = None  # 单系列斜纹豁免
        else:
            bar_colors = colors[i % len(colors)]
        if use_hatch and not (n_series == 1 and hatch_val is None):
            # GLM-5.2 blog style: ALL bars get hatching. glm-brand: 同系深色纹+边
            #（视觉精修）；其他主题保持黑色纹（历史行为）。
            bars = bar_func(x + offset, values, w, yerr=errs,
                            color=bar_colors,
                            edgecolor=_hatch_edgecolor(theme, bar_colors), linewidth=0.6,
                            hatch=hatch_val, capsize=3,
                            error_kw={'linewidth': 1},
                            label=name if n_series > 1 else None)
        else:
            bars = bar_func(x + offset, values, w, yerr=errs,
                            color=bar_colors, edgecolor='white', linewidth=0.5,
                            capsize=3, error_kw={'linewidth': 1},
                            label=name if n_series > 1 else None)
        all_bars.append((name, values, bars, offset))

        # v4.2 --peak-label：最大值点自动注记（数据事实，单/多系列均取全局峰）
        if kwargs.get("peak_label", False) and i == n_series - 1:
            _gl = next(iter(series))  # 全局峰所在系列
            _best, _bv = None, None
            for _n, _vals in series.items():
                for _j, _v in enumerate(_vals):
                    if _bv is None or float(_v) > _bv:
                        _best, _bv = (_n, _j), float(_v)
            if _best is not None:
                _annotate_peak(ax, list(range(len(labels))), labels, series[_best[0]],
                               horizontal, theme, cjk_fp,
                               series_name=_best[0] if n_series > 1 else None)

        # Value labels on bars
        if kwargs.get("show_values", False):
            for j, v in enumerate(values):
                err = errs[j] if errs and j < len(errs) else 0
                _fv = f'{int(v)}' if float(v).is_integer() else f'{v:.1f}'
                if horizontal:
                    ax.text(v + err + max(values) * 0.01, x[j] + offset,
                            _fv, ha='left', va='center', fontsize=7,
                            color=colors[i % len(colors)])
                else:
                    ax.text(x[j] + offset, v + err + max(values) * 0.01,
                            _fv, ha='center', va='bottom', fontsize=7,
                            color=colors[i % len(colors)])

    # Ratio annotations (e.g., "4.96x" above second series bars)
    if show_ratio and n_series >= 2:
        base_name = list(series.keys())[ratio_base]
        base_values = list(series.values())[ratio_base]
        for i, (name, values, bars, offset) in enumerate(all_bars):
            if i == ratio_base:
                continue
            for j, v in enumerate(values):
                bv = base_values[j] if j < len(base_values) else 0
                if bv != 0:
                    ratio = v / bv
                    ratio_str = f'{ratio:.2f}x' if ratio >= 1 else f'{ratio:.2f}x'
                    ratio_color = '#D55E00'
                    if horizontal:
                        ax.text(v + max(values) * 0.02, x[j] + offset,
                                ratio_str, ha='left', va='center', fontsize=8,
                                fontweight='bold', color=ratio_color)
                    else:
                        ax.text(x[j] + offset, v + max(values) * 0.02,
                                ratio_str, ha='center', va='bottom', fontsize=8,
                                fontweight='bold', color=ratio_color)

    # Significance brackets
    if significance:
        for key, label in significance.items():
            parts = key.split(":")
            if len(parts) == 2:
                grp_idx = int(parts[1])
            else:
                grp_idx = int(parts[0])
            if horizontal:
                x_top = ax.get_xlim()[1] * 0.95
                y_pos = x[grp_idx]
                fc = '#C0392B' if label not in ('NS', 'ns') else 'gray'
                fw = 'bold' if label not in ('NS', 'ns') else 'normal'
                ax.annotate(label, (x_top, y_pos), ha='left', va='center',
                            fontsize=8, fontweight=fw, color=fc)
            else:
                y_top = ax.get_ylim()[1] * 0.95
                fc = '#C0392B' if label not in ('NS', 'ns') else 'gray'
                fw = 'bold' if label not in ('NS', 'ns') else 'normal'
                ax.annotate(label, (x[grp_idx], y_top), ha='center', va='bottom',
                            fontsize=8, fontweight=fw, color=fc)

    if horizontal:
        y_fs = theme["font_size"] - 1
        if len(labels) > 12:
            y_fs -= 1
        ax.set_yticks(x)
        ax.set_yticklabels(labels, fontsize=y_fs,
                           fontproperties=cjk_fp if cjk_fp and any(has_cjk(l) for l in labels) else None)
        ax.invert_yaxis()
    else:
        max_lbl_len = max((len(str(l)) for l in labels), default=0)
        rotation = 45 if (len(labels) > 8 or max_lbl_len > 12) else 0
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=theme["font_size"] - 1,
                           rotation=rotation, ha='right' if rotation else 'center',
                           fontproperties=cjk_fp if cjk_fp and any(has_cjk(l) for l in labels) else None)


def gen_heatmap(data, ax, theme, cjk_fp, **kwargs):
    """Heatmap with text annotations."""
    matrix = data.get("matrix", data.get("data", data.get("values", None)))
    if matrix is None:
        # Fallback: build matrix from series (C2 fix — CSV heatmap support)
        series = data.get("series", {})
        if series:
            matrix = np.array(list(series.values()))
        else:
            matrix = np.array([])
    else:
        matrix = np.array(matrix)
    row_labels = data.get("row_labels", data.get("y_labels", data.get("rows", data.get("labels", []))))
    col_labels = data.get("col_labels", data.get("x_labels", data.get("cols", list(data.get("series", {}).keys()))))
    cmap = kwargs.get("cmap") or "RdBu_r"
    vmin = kwargs.get("vmin", None)
    vmax = kwargs.get("vmax", None)
    annot_fmt = kwargs.get("annot_format", "{:+.1f}")

    if matrix.size == 0:
        raise ValueError("heatmap: matrix is empty — provide 'matrix' (2D list) or 'series'")
    ax._af_category_axis = True  # 行列标签是数据：豁免 fix_tick_overlaps 降级

    has_neg = bool((matrix < 0).any())
    # Data-driven default: all-positive data uses a warm sequential colormap
    # (YlOrRd) — RdBu_r's white midpoint makes low positive values look like
    # a "broken band" (断层). Diverging colormaps are only sensible when the
    # data actually spans negative values.
    if cmap == "RdBu_r" and not has_neg and kwargs.get("cmap") is None:
        cmap = "YlOrRd"

    if vmin is None or vmax is None:
        if has_neg:
            abs_max = max(abs(matrix.min()), abs(matrix.max()))
            vmin = vmin if vmin is not None else -abs_max
            vmax = vmax if vmax is not None else abs_max
        else:
            vmin = vmin if vmin is not None else float(matrix.min())
            vmax = vmax if vmax is not None else float(matrix.max())

    im = ax.imshow(matrix, cmap=cmap, vmin=vmin, vmax=vmax, aspect='auto')

    # Text annotations
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix[i, j]
            color = 'white' if abs(v) > (abs(vmin) + abs(vmax)) / 2 * 0.7 else 'black'
            ax.text(j, i, annot_fmt.format(v), ha='center', va='center',
                    fontsize=9, fontweight='bold', color=color)

    ax.set_xticks(range(len(col_labels)))
    use_cjk_cols = cjk_fp and any(has_cjk(l) for l in col_labels)
    max_col_len = max((len(str(l)) for l in col_labels), default=0)
    rot = 45 if (len(col_labels) > 6 or max_col_len > 14) else 0
    ax.set_xticklabels(col_labels, fontsize=theme["font_size"] - 2,
                       rotation=rot, ha='right' if rot else 'center',
                       fontproperties=cjk_fp if use_cjk_cols else None)
    ax.set_yticks(range(len(row_labels)))
    use_cjk_rows = cjk_fp and any(has_cjk(l) for l in row_labels)
    ax.set_yticklabels(row_labels, fontsize=theme["font_size"],
                       fontproperties=cjk_fp if use_cjk_rows else None)

    return im  # for colorbar


def gen_scatter(data, ax, theme, cjk_fp, **kwargs):
    """Scatter plot with optional trend line and grouping."""
    x_data = np.array(data.get("x", data.get("xs", [])))
    y_data = np.array(data.get("y", data.get("ys", [])))
    groups = data.get("groups", data.get("colors", None))

    if groups is None:
        ax.scatter(x_data, y_data, s=60, color=theme["colors"][0],
                   edgecolors='white', linewidth=0.5, alpha=0.7, zorder=3)
    else:
        # Validate groups length matches x/y data length
        n = min(len(x_data), len(y_data))
        if len(groups) > n:
            groups = groups[:n]
        unique_groups = list(dict.fromkeys(groups))  # preserve order
        for i, g in enumerate(unique_groups):
            mask = [j for j in range(len(groups)) if groups[j] == g]
            c = theme["colors"][i % len(theme["colors"])]
            ax.scatter(x_data[mask], y_data[mask], s=60, c=c,
                       edgecolors='white', linewidth=0.5, alpha=0.7,
                       label=g, zorder=3)

    # Point labels (data["labels"] — one per (x, y) point)
    point_labels = data.get("labels", [])
    if point_labels and len(point_labels) == len(x_data):
        use_cjk = cjk_fp and any(has_cjk(str(l)) for l in point_labels)
        n_pts = len(x_data)
        for i, (xi, yi, lab) in enumerate(zip(x_data, y_data, point_labels)):
            # Alternate above/below to keep neighbors readable; offset grows
            # with index so clustered points (e.g. years 1950/1953/1955) don't collide.
            row = i // 2  # every other point flips side
            dy = 10 + 3 * row if i % 2 == 0 else -13 - 3 * row
            ax.annotate(str(lab), xy=(xi, yi), xytext=(0, dy),
                        textcoords='offset points', fontsize=6.5,
                        ha='center', va='center', zorder=5,
                        fontproperties=cjk_fp if use_cjk else None,
                        color='#444444', alpha=0.9)

    # Trend line
    if kwargs.get("trend", True) and len(x_data) >= 3:
        z = np.polyfit(x_data, y_data, 1)
        p = np.poly1d(z)
        x_line = np.linspace(x_data.min(), x_data.max(), 100)
        ax.plot(x_line, p(x_line), '--', color='gray', alpha=0.6, linewidth=1.2,
                zorder=2, label='Linear trend')
        r = np.corrcoef(x_data, y_data)[0, 1]
        ax.text(0.95, 0.05, f'r = {r:.3f}', transform=ax.transAxes,
                ha='right', va='bottom', fontsize=9, fontstyle='italic', color='gray',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8, edgecolor='lightgray'))

    # Mean points
    if groups and kwargs.get("show_mean", False):
        unique_groups = list(dict.fromkeys(groups))
        for i, g in enumerate(unique_groups):
            mask = [j for j in range(len(groups)) if groups[j] == g]
            mx, my = np.mean(x_data[mask]), np.mean(y_data[mask])
            c = theme["colors"][i % len(theme["colors"])]
            ax.scatter(mx, my, s=150, c=c, edgecolors='black', linewidth=1.2,
                       marker='o', zorder=4)

    ax.xaxis.grid(True, alpha=theme["grid_alpha"], linestyle='--')


def gen_line(data, ax, theme, cjk_fp, **kwargs):
    """Line chart with optional error bands."""
    labels = data.get("labels", data.get("x", []))
    series = data.get("series", data.get("datasets", {}))
    error_data = data.get("errors", {})
    markers = ['o', 's', 'D', '^', 'v', 'p', '*', 'h', '+', 'x']

    x = np.arange(len(labels)) if not any(isinstance(l, (int, float)) for l in labels) else np.array(labels)

    _line_ends = []  # v3.4 直接标注收集器
    for i, (name, values) in enumerate(series.items()):
        c = theme["colors"][i % len(theme["colors"])]
        mk = markers[i % len(markers)]
        lw = kwargs.get("linewidth", 2)
        ax.plot(x, values, c=c, marker=mk, markersize=6, linewidth=lw, label=name, zorder=3)

        # Error band/fill
        if name in error_data and error_data[name]:
            errs = error_data[name]
            if isinstance(errs, list) and len(errs) == len(values):
                lower = [v - e for v, e in zip(values, errs)]
                upper = [v + e for v, e in zip(values, errs)]
                ax.fill_between(x, lower, upper, color=c, alpha=0.15, zorder=2)
        if kwargs.get("direct_label"):
            _line_ends.append((str(name), values[-1], c))

    # ── v3.4：直接标注（线末端系列名，自动上下避让，替代图例框）──
    if kwargs.get("direct_label") and _line_ends:
        _span = (max(v for _, v, _ in _line_ends) - min(v for _, v, _ in _line_ends)) or 1.0
        _gap = _span * 0.08
        _order = sorted(range(len(_line_ends)), key=lambda i: _line_ends[i][1])
        _adj = {i: _line_ends[i][1] for i in _order}
        for _a, _b in zip(_order, _order[1:]):
            if _adj[_b] - _adj[_a] < _gap:
                _adj[_b] = _adj[_a] + _gap
        _x_span = (max(x) - min(x)) or 1.0
        ax.set_xlim(right=max(x) + _x_span * 0.22)
        _any_cjk = cjk_fp and any(has_cjk(n) for n, _, _ in _line_ends)
        for _i, (_name, _v, _c) in enumerate(_line_ends):
            ax.annotate(_name, xy=(max(x) + _x_span * 0.03, _adj[_i]),
                        textcoords="data", color=_c, fontweight="bold",
                        fontsize=theme["font_size"] - 1, va="center", ha="left",
                        fontproperties=cjk_fp if _any_cjk else None,
                        annotation_clip=False)

    # ── v4.2 --peak-label：全局最大值点注记（数据事实）──
    if kwargs.get("peak_label") and series:
        _best_n, _best_i = None, None
        for _n, _vals in series.items():
            for _j, _v in enumerate(_vals):
                if _best_i is None or float(_v) > float(_best_v):
                    _best_n, _best_i, _best_v = _n, _j, _v
        _annotate_peak(ax, list(x), labels, series[_best_n], False, theme, cjk_fp,
                       series_name=_best_n if len(series) > 1 else None)

    ax.set_xticks(x if not any(isinstance(l, (int, float)) for l in labels) else range(len(labels)))
    if not any(isinstance(l, (int, float)) for l in labels):
        use_cjk = cjk_fp and any(has_cjk(l) for l in labels)
        rot = 45 if len(labels) > 10 else 0
        ax.set_xticklabels(labels, fontsize=theme["font_size"] - 1,
                           rotation=rot, ha='right' if rot else 'center',
                           fontproperties=cjk_fp if use_cjk else None)


def gen_box(data, ax, theme, cjk_fp, **kwargs):
    """Box plot with optional jitter points."""
    labels = data.get("labels", data.get("x", []))
    series = data.get("series", data.get("datasets", {}))

    positions = list(range(len(series)))
    bp = ax.boxplot(list(series.values()), positions=positions, widths=0.5,
                    patch_artist=True, showfliers=False)

    for i, (patch, name) in enumerate(zip(bp['boxes'], series.keys())):
        patch.set_facecolor(theme["colors"][i % len(theme["colors"])])
        patch.set_alpha(0.6)

    # Jitter points
    rng = np.random.default_rng(42)
    for i, (name, values) in enumerate(series.items()):
        vals = np.array(values, dtype=float)
        jitter_x = positions[i] + rng.normal(0, 0.06, len(vals))
        c = theme["colors"][i % len(theme["colors"])]
        ax.scatter(jitter_x, vals, s=18, c=c, alpha=0.5, zorder=3, edgecolors='none')

    ax.set_xticks(positions)
    use_cjk = cjk_fp and any(has_cjk(l) for l in series.keys())
    ax.set_xticklabels(list(series.keys()), fontsize=theme["font_size"] - 1,
                       fontproperties=cjk_fp if use_cjk else None)

    if kwargs.get("stats_multi"):
        annotate_multi_stats(ax, series, positions, theme, "box")
    elif kwargs.get("stats_auto"):
        annotate_auto_stats(ax, series, positions, theme, "box")
    elif kwargs.get("stats_bootstrap"):
        annotate_bootstrap_stats(ax, series, positions, theme, "box")


def gen_forest(data, ax, theme, cjk_fp, **kwargs):
    """Forest plot for meta-analysis with weights, heterogeneity, and events."""
    ax._af_category_axis = True  # 研究名 y 轴是数据：豁免防重叠抽稀（与热图同机制）
    labels = data.get("labels", data.get("studies", []))
    estimates = data.get("estimates", data.get("values", []))
    ci_low = data.get("ci_low", data.get("lower", []))
    ci_high = data.get("ci_high", data.get("upper", []))
    weights = data.get("weights", None)  # Study weights for bubble size
    overall = data.get("overall", None)
    measure = data.get("measure", "OR")  # Effect measure label: OR, RR, HR, MD, SMD
    # v2.6.0 审核修复：缺省无效线按效应尺度自动取值——比率尺度（OR/RR/HR）无效线
    # 是 1.0，差值尺度（MD/SMD）是 0.0；旧默认恒取 0 会把自然尺度 OR/HR 的
    # "CI 是否跨过 1"画错位置，误导显著性判读。显式 ref_line 永远优先。
    ref_line = data.get("ref_line", None)
    if ref_line is None:
        ref_line = 0.0 if str(measure).upper() in ("MD", "SMD") else 1.0
        print(f"forest: 未指定 ref_line，按效应尺度 {measure} 自动取无效线 {ref_line:g}"
              f"（log 尺度数据请显式传 ref_line=0）", file=sys.stderr)
    heterogeneity = data.get("heterogeneity", None)  # {"Q": float, "df": int, "I2": float, "p": float}
    events = data.get("events", None)  # [{"events": int, "total": int}, ...] per study
    use_hatch = kwargs.get("hatch", False)

    # ── v2.4.0：留一法敏感性分析（--sensitivity）──
    if kwargs.get("sensitivity") and _afstats is not None:
        se_per_study = data.get("se_list", data.get("ses", None))
        if se_per_study is None and len(ci_low) == len(ci_high) == len(estimates) and len(estimates) >= 4:
            se_per_study = [(float(h) - float(l)) / 3.92
                            for l, h in zip(ci_low, ci_high)]
            print("WARNING: forest: --sensitivity 由 95%CI 反推 se（近似 (hi-lo)/3.92）；"
                  "有精确 se 请在数据提供 se_list", file=sys.stderr)
        loo = None
        if se_per_study is None or len(se_per_study) != len(estimates):
            print("WARNING: forest: --sensitivity 需要 se_list 或可反推的对称 CI，已跳过",
                  file=sys.stderr)
        else:
            try:
                loo = _afstats.leave_one_out(estimates, se_per_study)
            except ValueError as e:
                print(f"WARNING: forest: 留一法无法计算：{e}", file=sys.stderr)
        if loo:
            for gi, (omi, pooled, plo, phi) in enumerate(loo):
                y = -(gi + 2)
                ax.plot([plo, phi], [y, y], color="#888888", lw=1.4, zorder=3)
                ax.scatter([pooled], [y], s=46, marker="D",
                           color=theme["colors"][1 % len(theme["colors"])],
                           edgecolor="#5B6770", linewidth=0.8, zorder=4)
                _lbl = (labels[omi] if isinstance(labels, list) and omi < len(labels)
                        else f"Study {omi+1}")
                ax.text(-0.02, y, f"省略{_lbl}", transform=ax.get_yaxis_transform(),
                        ha="right", va="center",
                        fontsize=max(6, theme["font_size"] - 1),
                        fontproperties=cjk_fp if cjk_fp and has_cjk(str(_lbl)) else None,
                        color="#555555")
            ax.axhline(-1.2, color="#CCCCCC", lw=0.8, linestyle="--")
            ax.text(-0.02, -1.55, "留一法敏感性分析（省略单研究后的随机效应合并）",
                    transform=ax.get_yaxis_transform(), ha="right", va="center",
                    fontsize=max(6.5, theme["font_size"] - 1),
                    fontproperties=cjk_fp if cjk_fp and has_cjk("留一") else None,
                    color="#8a6414")
            ax.set_ylim(-(len(loo) + 3.2), None)
            print(f"forest: 留一法敏感性分析 {len(loo)} 组已绘制（可见性依赖各研究效应单位一致）",
                  file=sys.stderr)

    n_studies = len(labels)
    y_pos = list(range(n_studies))

    # Calculate weight-based bubble sizes if weights provided
    if weights and len(weights) == n_studies:
        w_arr = np.array(weights, dtype=float)
        w_min, w_max = w_arr.min(), w_arr.max()
        if w_max > w_min:
            bubble_sizes = 40 + (w_arr - w_min) / (w_max - w_min) * 160  # 40-200 range
        else:
            bubble_sizes = np.full(n_studies, 80.0)
    else:
        bubble_sizes = np.full(n_studies, 80.0)

    # Column layout: leave space for events column on left
    plot_x_start = 0.0
    events_col_x = None
    if events and len(events) == n_studies:
        events_col_x = -0.3  # Relative position in axes coords, handled via text

    for i, (est, lo, hi) in enumerate(zip(estimates, ci_low, ci_high)):
        # CI whisker line
        ax.plot([lo, hi], [i, i], '-', color=theme["colors"][0], linewidth=1.5, zorder=2)
        # Weighted point estimate (bubble)
        ax.scatter(est, i, c=theme["colors"][0], s=bubble_sizes[i], zorder=3,
                   edgecolors='black', linewidth=0.5)
        # Effect estimate annotation on right
        ax.text(hi + (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.02, i,
                f'{est:.2f} [{lo:.2f}, {hi:.2f}]', va='center', fontsize=8)
        # Events/Total on left (if provided)
        if events and i < len(events):
            ev = events[i]
            ev_str = f"{ev.get('events', '?')}/{ev.get('total', '?')}" if isinstance(ev, dict) else str(ev)
            ax.annotate(ev_str, xy=(0, 0), xytext=(-0.15, i),
                        textcoords=('axes fraction', 'data'),
                        ha='right', va='center', fontsize=7, color='#555555')

    # Reference line
    ax.axvline(x=ref_line, color='gray', linestyle='--', linewidth=1, alpha=0.6)

    # Separator line before overall
    if overall:
        ax.axhline(y=n_studies - 0.5, color='#333333', linewidth=0.8, alpha=0.5)

    # Overall diamond
    if overall:
        oy = n_studies
        est_o = overall["estimate"]
        lo_o = overall["ci_low"]
        hi_o = overall["ci_high"]
        diamond_x = [lo_o, est_o, hi_o, est_o, lo_o]
        diamond_y = [oy, oy - 0.2, oy, oy + 0.2, oy]
        ax.fill(diamond_x, diamond_y, color=theme["colors"][1], alpha=0.7, zorder=4,
                hatch=HATCH_PATTERNS[1] if use_hatch else None)
        ax.text(hi_o + (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.02, oy,
                f'Overall: {est_o:.2f} [{lo_o:.2f}, {hi_o:.2f}]', va='center',
                fontsize=9, fontweight='bold')

    # Heterogeneity annotation
    if heterogeneity:
        i2 = heterogeneity.get("I2", None)
        q_val = heterogeneity.get("Q", None)
        df_val = heterogeneity.get("df", None)
        p_val = heterogeneity.get("p", None)
        parts = []
        if i2 is not None:
            parts.append(f"I² = {i2:.1f}%")
        if q_val is not None and df_val is not None:
            parts.append(f"Q = {q_val:.2f}, df = {df_val}")
        if p_val is not None:
            parts.append(f"p = {p_val:.3f}" if p_val >= 0.001 else f"p < 0.001")
        if parts:
            het_text = "Heterogeneity: " + "; ".join(parts)
            ax.text(0.5, -0.12, het_text, transform=ax.transAxes,
                    ha='center', va='top', fontsize=7, fontstyle='italic', color='#555555')

    # X-axis label with measure type
    ax.set_xlabel(measure, fontsize=theme["font_size"])

    # Column header for events
    if events and len(events) > 0:
        ax.annotate("Events/Total", xy=(0, 0), xytext=(-0.15, -0.8),
                    textcoords=('axes fraction', 'data'),
                    ha='right', va='center', fontsize=7, fontweight='bold', color='#333333')

    all_labels = list(labels) + (["Overall"] if overall else [])
    ax.set_yticks(list(y_pos) + ([n_studies] if overall else []))
    use_cjk = cjk_fp and any(has_cjk(l) for l in all_labels)
    ax.set_yticklabels(all_labels, fontsize=theme["font_size"],
                       fontproperties=cjk_fp if use_cjk else None)
    ax.invert_yaxis()


def gen_violin(data, ax, theme, cjk_fp, **kwargs):
    """Violin plot with optional inner box and jitter points."""
    labels = data.get("labels", data.get("x", []))
    series = data.get("series", data.get("datasets", {}))

    positions = list(range(len(series)))
    values_list = list(series.values())

    vp = ax.violinplot(values_list, positions=positions, widths=0.6,
                       showmeans=kwargs.get("show_means", True),
                       showmedians=kwargs.get("show_medians", True),
                       showextrema=kwargs.get("show_extrema", True))

    # Color the violin bodies
    for i, body in enumerate(vp['bodies']):
        body.set_facecolor(theme["colors"][i % len(theme["colors"])])
        body.set_alpha(0.6)
        body.set_edgecolor(theme["colors"][i % len(theme["colors"])])
        body.set_linewidth(1)

    # Style internal lines
    for part in ['cmeans', 'cmedians', 'cmins', 'cmaxes', 'cbars']:
        if part in vp:
            vp[part].set_color('#333333')
            vp[part].set_linewidth(1)

    ax.set_xticks(positions)
    use_cjk = cjk_fp and any(has_cjk(l) for l in series.keys())
    ax.set_xticklabels(list(series.keys()), fontsize=theme["font_size"] - 1,
                       fontproperties=cjk_fp if use_cjk else None)

    if kwargs.get("stats_multi"):
        annotate_multi_stats(ax, series, positions, theme, "violin")
    elif kwargs.get("stats_auto"):
        annotate_auto_stats(ax, series, positions, theme, "violin")
    elif kwargs.get("stats_bootstrap"):
        annotate_bootstrap_stats(ax, series, positions, theme, "violin")


def _km_note_box(ax, text, cjk_fp=None):
    """KM 右上角注释框（log-rank/中位生存）：实测宽度自适应字号，
    保证不越出坐标区、不压 y 轴刻度；不透明底+高 zorder 防曲线横穿文字。"""
    fs = 8.0
    t = None
    for _ in range(7):
        if t is not None:
            t.remove()
        t = ax.text(0.97, 0.96, text, transform=ax.transAxes, ha="right", va="top",
                    fontsize=fs, fontstyle="italic", color="#333333", zorder=6,
                    fontproperties=cjk_fp if (cjk_fp and has_cjk(text)) else None,
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=1.0,
                              edgecolor="lightgray"))
        fig = ax.figure
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        bb = t.get_window_extent(renderer=renderer)
        ax_bb = ax.get_window_extent(renderer=renderer)
        if bb.x0 >= ax_bb.x0 or fs <= 6.0:
            break
        fs -= 0.5
    return t


def gen_km(data, ax, theme, cjk_fp, **kwargs):
    """Kaplan-Meier 生存曲线（v2.3：自动风险表 + 自动 log-rank）。

    原始数据格式（每样本 [时间, 事件]）>=2 组时自动做 Mantel-Haenszel
    log-rank 检验并在图内标注；主图下方以独立坐标轴渲染"Number at risk"
    风险表（主流程经 --no-risk-table 可关闭，--risk-times 自定义显示时间点）。
    仍兼容：用户直接提供 risk_table/log_rank（优先采用，不重复计算）、
    预计算 survival 曲线格式（无原始数据时跳过自动统计并提示）。
    """
    groups = data.get("groups", data.get("series", {}))
    risk_table = data.get("risk_table", None)      # 兼容 v2.2 用户供表
    log_rank = data.get("log_rank", None)
    median_survival = data.get("median_survival", None)
    risk_axes = kwargs.get("risk_axes", None)
    want_risk = kwargs.get("risk_table", True)
    risk_times_arg = kwargs.get("risk_times", None)

    if isinstance(groups, dict):
        group_names = list(groups.keys())
    elif isinstance(groups, list):
        group_names = data.get("labels", [f"Group {i+1}" for i in range(len(groups))])
        groups = dict(zip(group_names, groups))
        bad = [g for g in groups.values()
               if not (isinstance(g, (list, tuple)) and
                       all(isinstance(p, (list, tuple)) and len(p) >= 2 and
                           all(isinstance(n, (int, float)) for n in p) for p in g) or
                       all(isinstance(n, (int, float)) for n in g))]
        if bad:
            raise ValueError(
                "km: unsupported 'groups' format. Expected {\"Group\": [[t, s], ...]} "
                "or [t1, t2, ...] per group — got object list like "
                "[{\"label\": ..., \"time\": ..., \"events\": ...}]. "
                "Convert to {\"组名\": [[t, s], ...]}.")
    else:
        group_names = []
        groups = {}

    raw_groups = {}     # 组名 -> (times, events)
    precomputed = False
    if not groups and "time" in data and "survival" in data:
        precomputed = True
        surv_data = data["survival"]
        cens_data = data.get("censored", {})
        group_names = list(surv_data.keys())
        for gname in group_names:
            t_arr = np.asarray(data["time"], dtype=float)
            s_arr = np.asarray(surv_data[gname], dtype=float)
            c_arr = np.asarray(cens_data.get(gname, [0] * len(s_arr)), dtype=float)
            c = theme["colors"][group_names.index(gname) % len(theme["colors"])]
            ax.step(t_arr, s_arr, where='post', color=c, linewidth=2, label=gname, zorder=3)
            _cm = (c_arr[:len(t_arr)] == 1)
            if _cm.any():
                ax.scatter(t_arr[:len(t_arr)][_cm], s_arr[:len(t_arr)][_cm],
                           marker='+', color=c, s=30, linewidth=1.5, zorder=4)
        if risk_axes is None or not want_risk:
            print("WARNING: km: 预计算 survival 格式无原始数据，无法自动计算风险表/"
                  "log-rank——请提供 {组: [[时间,事件], ...]} 原始格式", file=sys.stderr)
    else:
        for gname in group_names:
            raw = groups.get(gname, None)
            if not isinstance(raw, (list, tuple)) or len(raw) == 0:
                continue
            if isinstance(raw[0], (list, tuple)):
                times = np.array([p[0] for p in raw], dtype=float)
                second = np.array([p[1] for p in raw], dtype=float)
                # v3.7：竞争风险编码（整数且含 ≥2）优先于预计算判定——
                # 此前含 2 的原始数据被误当预计算生存概率静默绘制
                _is_int_code = np.all(second == np.floor(second)) and np.any(second >= 2)
                if np.all(np.isin(second, (0.0, 1.0))):
                    raw_groups[gname] = (times, second)   # [时间, 事件0/1]
                elif _is_int_code:
                    raw_groups[gname] = (times, second)   # [时间, 事件0/1/2+竞争风险]
                else:
                    # [时间, 预计算生存概率]：直接阶梯绘制（v2.2 曾误当事件数，
                    # 曲线数学错误；v2.3 起正确识别），不计入自动统计
                    c = theme["colors"][group_names.index(gname) % len(theme["colors"])]
                    ax.step(times, second, where='post', color=c, linewidth=2,
                            label=gname, zorder=3)
                    print(f"WARNING: km: '{gname}' 第二列为连续值，按预计算生存概率绘制"
                          "（无原始数据，跳过自动风险表/log-rank）", file=sys.stderr)
                continue
            times = np.array(raw, dtype=float)
            raw_groups[gname] = (times, np.ones(len(times)))

        # ── v3.7：竞争风险检测（任一组 events 含 ≥2 编码 → Aalen-Johansen CIF 模式）──
        _competing = any(
            np.any(np.asarray(ev) >= 2)
            for (_t, ev) in raw_groups.values() if len(ev) == len(_t))
        if _competing and _afstats is not None:
            _cn_src = data.get("cause_names") if isinstance(data, dict) else None
            _cause_names = _cn_src if isinstance(_cn_src, dict) else {}
            print("[auto] km: 检测到竞争风险事件编码（≥2）——切换 Aalen-Johansen "
                  "累计发生率曲线（每因一条）", file=sys.stderr)
            for i, gname in enumerate(group_names):
                if gname not in raw_groups:
                    continue
                c = theme["colors"][i % len(theme["colors"])]
                times, events = raw_groups[gname]
                _aj = _afstats.aalen_johansen(times, events)
                for j, state in enumerate(sorted(_aj["cif"].keys())):
                    _cl = _cause_names.get(state) if isinstance(_cause_names, dict) else None
                    label = _cl or (f"{gname}·原因{state}" if state >= 2 else f"{gname}·目标事件")
                    ax.step(_aj["times"], _aj["cif"][state], where="post",
                            color=theme["colors"][(i * 3 + j) % len(theme["colors"])],
                            linewidth=2, label=label, zorder=3)
                _ttl = (kwargs.get("competing_title")
                        or f"{gname}: 累计发生率（Aalen-Johansen，竞争风险）")
                if i == 0:
                    ax.set_title(_ttl, fontsize=theme["font_size"],
                                 fontproperties=cjk_fp if cjk_fp and has_cjk(_ttl) else None)
            ax.set_ylabel("累计发生率 Cumulative Incidence",
                          fontsize=theme["font_size"] - 1,
                          fontproperties=cjk_fp if cjk_fp else None)
            return  # AJ 模式独立渲染，不走 KM 主循环

        for i, gname in enumerate(group_names):
            if gname not in raw_groups:
                continue
            c = theme["colors"][i % len(theme["colors"])]
            times, events = raw_groups[gname]
            if _afstats is not None:
                t_seq, s_seq, censor_pts = _afstats.km_estimate(times, events)
            else:
                order = np.argsort(times, kind="stable")
                ts, es = times[order], events[order]
                surv, t_seq, s_seq, censor_pts = 1.0, [0.0], [1.0], []
                n_risk = len(ts)
                for ut in np.unique(ts):
                    m = ts == ut
                    d = float(es[m].sum())
                    n_c = int(m.sum() - d)
                    if n_risk > 0 and d > 0:
                        surv *= 1 - d / n_risk
                    if n_c:
                        censor_pts.append((float(ut), surv))
                    t_seq.append(float(ut)); s_seq.append(surv)
                    n_risk -= int(m.sum())
            ax.step(t_seq, s_seq, where='post', color=c, linewidth=2, label=gname, zorder=3)
            if censor_pts:
                _cts, _css = zip(*censor_pts)
                ax.scatter(_cts, _css, marker='+', color=c, s=30, linewidth=1.5, zorder=4)
            if median_survival and gname in median_survival and median_survival[gname] is not None:
                ax.axvline(x=float(median_survival[gname]), color=c, linestyle=':',
                           alpha=0.4, linewidth=1)

    # 参考线（中位生存 0.5）
    ax.axhline(y=0.5, color='gray', linestyle='--', alpha=0.3, linewidth=0.8)

    # ── 自动 log-rank（原始数据 >=2 组且用户未提供时）──
    if log_rank is None and len(raw_groups) >= 2 and _afstats is not None:
        try:
            chi2_v, p_lr, df_lr = _afstats.logrank_test(raw_groups)
            log_rank = {"p": p_lr, "method": "log-rank"}
            print(f"km: log-rank 检验：chi2={chi2_v:.3g}, df={df_lr}, p={p_lr:.4g}",
                  file=sys.stderr)
        except Exception as e:
            print(f"WARNING: km: log-rank 自动计算失败（{e}），跳过标注", file=sys.stderr)

    # ── 自动中位生存（原始数据组；用户传 median_survival 仍画竖线，互不冲突）──
    median_notes = []
    if kwargs.get("median_auto", True) and raw_groups and _afstats is not None:
        for gname in group_names:
            if gname not in raw_groups or (median_survival and gname in median_survival):
                continue
            t_g, e_g = raw_groups[gname]
            try:
                med, clo, chi_ = _afstats.km_median_survival(t_g, e_g)
            except Exception:
                med = None
            if med is None:
                median_notes.append(f"{gname}: 未到达")
            else:
                if clo is not None and chi_ is not None:
                    median_notes.append(f"{gname}: {med:g}（{clo:g}~{chi_:g}）")
                else:
                    median_notes.append(f"{gname}: {med:g}")
                if median_survival is None:
                    median_survival = {}
                median_survival.setdefault(gname, med)
        if median_notes:
            print("km: 自动中位生存（95%CI）：" + "；".join(median_notes), file=sys.stderr)
        if log_rank is not None:
            method = log_rank.get("method", "log-rank")
            p_val = log_rank.get("p")
            try:
                p_val = float(p_val)
            except (ValueError, TypeError):
                p_val = 1.0
            p_str = f"p = {p_val:.3f}" if p_val >= 0.001 else "p < 0.001"
            sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else "NS"
            _box_lines = [f"{method} {p_str}{sig}"]
            if median_notes:
                _box_lines.append("中位生存（95%CI）")
                _box_lines += median_notes[:4]
            _km_note_box(ax, "\n".join(_box_lines), cjk_fp)
            median_notes = []
        if median_notes:
            _km_note_box(ax, "中位生存（95%CI）\n" + "\n".join(median_notes[:4]), cjk_fp)

    # ── 风险表（自动计算；独立坐标轴与主图共享 x 轴）──
    rendered = False
    if want_risk and raw_groups and risk_axes is not None and _afstats is not None:
        try:
            if risk_times_arg:
                if isinstance(risk_times_arg, str):
                    disp_times = [float(x) for x in risk_times_arg.split(",") if x.strip()]
                else:
                    disp_times = [float(x) for x in risk_times_arg]
            else:
                all_t = np.concatenate([t for t, _ in raw_groups.values()])
                disp_times = _afstats.default_risk_times(all_t, k=5)
            ax.set_xlim(left=0)
            x_max = ax.get_xlim()[1]
            rows = []
            for gname in group_names:
                if gname not in raw_groups:
                    continue
                t_g, e_g = raw_groups[gname]
                col = theme["colors"][group_names.index(gname) % len(theme["colors"])]
                rows.append((gname, _afstats.km_at_risk(t_g, e_g, disp_times), col))
            ra = risk_axes
            ra.set_xlim(0, x_max)
            ra.set_ylim(0, max(len(rows), 1))
            ra.invert_yaxis()
            for sp in ra.spines.values():
                sp.set_visible(False)
            ra.set_yticks([])
            ra.tick_params(axis="x", labelbottom=False, length=0)
            ra.grid(False)
            _hdr_txt = ("Number at risk（处于风险人数）"
                        if any(has_cjk(str(g)) for g, _, _ in rows) or bool(cjk_fp)
                        else "Number at risk")
            _fp_hdr = cjk_fp if cjk_fp and has_cjk(_hdr_txt) else None
            ra.text(0.0, -0.66, _hdr_txt,
                    fontsize=max(7, theme["font_size"] - 1), fontweight="bold",
                    color="#333333", ha="left", va="center", fontproperties=_fp_hdr,
                    clip_on=False)
            # 组名实测定位（修复组名与首列数字黏连）：右缘 = 首列数字左缘 - 间距
            ra.figure.canvas.draw()
            _renderer = ra.figure.canvas.get_renderer()
            _inv_data = ra.transData.inverted()
            _num_fs = max(6.5, theme["font_size"] - 1.5)
            _t0 = min(disp_times)
            _first_w = 0.0
            for _g, _counts, _c in rows:
                _p = ra.text(_t0, 0.5, str(_counts[0]), fontsize=_num_fs,
                             ha="center", va="center")
                _bb = _p.get_window_extent(renderer=_renderer).transformed(_inv_data)
                _first_w = max(_first_w, _bb.width)
                _p.remove()
            _name_right = _t0 - _first_w / 2 - x_max * 0.02
            for ri, (gname, counts, col) in enumerate(rows):
                y = ri + 0.5
                _fp_g = cjk_fp if cjk_fp and has_cjk(str(gname)) else None
                ra.text(_name_right, y, str(gname), fontsize=max(6.5, theme["font_size"] - 1.5),
                        color=col, ha="right", va="center", fontweight="bold",
                        fontproperties=_fp_g, clip_on=False)
                for t_v, cnt in zip(disp_times, counts):
                    if t_v <= x_max:
                        ra.text(t_v, y, str(cnt),
                                fontsize=max(6.5, theme["font_size"] - 1.5),
                                color="#333333", ha="center", va="center")
            rendered = True
        except Exception as e:
            print(f"WARNING: km: 自动风险表渲染失败（{e}）", file=sys.stderr)

    # ── 兼容 v2.2：用户直接提供 risk_table 且无自动表时的文本模式 ──
    if not rendered and risk_table and isinstance(risk_table, dict):
        rt_times = risk_table.get("times", [])
        ax.text(0.02, -0.08, "Number at risk", transform=ax.transAxes,
                fontsize=7, fontweight='bold', color='#333333')
        for i, gname in enumerate(group_names):
            c = theme["colors"][i % len(theme["colors"])]
            n_at = risk_table.get(gname, [])
            rt_str = "  ".join(str(n) for n in n_at)
            ax.text(0.02, -0.08 - (i + 1) * 0.04, f"{gname}: {rt_str}",
                    transform=ax.transAxes, fontsize=6, color=c)

    ax.set_ylim(-0.02, 1.02)
    ax.set_xlim(left=0)
    ax.xaxis.grid(True, alpha=theme["grid_alpha"], linestyle='--')


def gen_roc(data, ax, theme, cjk_fp, **kwargs):
    """ROC curve with AUC value, confidence interval, and optimal cutoff."""
    curves = data.get("curves", None)  # list of curve objects
    single_fpr = data.get("fpr", data.get("x", None))
    single_tpr = data.get("tpr", data.get("y", None))
    single_auc = data.get("auc", None)
    ci = data.get("ci", None)  # {"low": 0.82, "high": 0.94}
    cutoff = data.get("cutoff", None)  # {"fpr": 0.15, "tpr": 0.88, "threshold": 2.35}
    diagonal = data.get("diagonal", True)  # show diagonal reference line

    # Support single curve (fpr/tpr arrays) or multiple curves
    if curves is None and single_fpr is not None and single_tpr is not None:
        fpr_arr = np.array(single_fpr, dtype=float)
        tpr_arr = np.array(single_tpr, dtype=float)
        auc_val = single_auc

        # Compute AUC if not provided
        if auc_val is None:
            auc_val = np.trapezoid(tpr_arr, fpr_arr) if hasattr(np, 'trapezoid') else np.trapz(tpr_arr, fpr_arr)

        ax.plot(fpr_arr, tpr_arr, color=theme["colors"][0], linewidth=2.5, zorder=3,
                label=f'AUC = {auc_val:.3f}')

        # CI annotation
        if ci:
            ci_low = ci.get("low", ci.get("ci_low", None))
            ci_high = ci.get("high", ci.get("ci_high", None))
            if ci_low is not None and ci_high is not None:
                ax.text(0.95, 0.05, f'95% CI: [{ci_low:.3f}, {ci_high:.3f}]',
                        transform=ax.transAxes, ha='right', va='bottom',
                        fontsize=8, color='#555555',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9, edgecolor='lightgray'))

        # Optimal cutoff point
        if cutoff:
            co_fpr = cutoff.get("fpr", None)
            co_tpr = cutoff.get("tpr", None)
            co_thr = cutoff.get("threshold", None)
            if co_fpr is not None and co_tpr is not None:
                ax.scatter(co_fpr, co_tpr, color=theme["colors"][0], s=80, zorder=5,
                           edgecolors='black', linewidth=1, marker='o')
                label_parts = [f'Optimal cutoff']
                if co_thr is not None:
                    label_parts.append(f'threshold = {co_thr}')
                ax.annotate('\n'.join(label_parts), (co_fpr, co_tpr),
                            textcoords='offset points', xytext=(10, -15),
                            fontsize=7, color='#555555',
                            arrowprops=dict(arrowstyle='->', color='gray', lw=0.8))

    elif curves:
        # Multiple ROC curves
        _seen_labels = set()
        for i, curve in enumerate(curves):
            fpr_c = np.array(curve.get("fpr", curve.get("x", [])), dtype=float)
            tpr_c = np.array(curve.get("tpr", curve.get("y", [])), dtype=float)
            auc_c = curve.get("auc", None)
            name = curve.get("name", f'Model {i+1}')

            if auc_c is None:
                auc_c = np.trapezoid(tpr_c, fpr_c) if hasattr(np, 'trapezoid') else np.trapz(tpr_c, fpr_c)

            c = theme["colors"][i % len(theme["colors"])]
            label = f'{name} (AUC={auc_c:.3f})'
            # B3(v2.7)：两条曲线 AUC 相同（或同名）时图例标签会完全重复——
            # 自动加序号消歧并 stderr 告知，避免图例两条一模一样无法区分
            if label in _seen_labels:
                uniq = f'{label} #{i + 1}'
                k = 2
                while uniq in _seen_labels:
                    uniq = f'{label} #{k + 1}'
                    k += 1
                print(f"WARNING: ROC 曲线「{name}」图例标签重复（AUC 相同或同名），"
                      f"已自动消歧为「{uniq}」", file=sys.stderr)
                label = uniq
            _seen_labels.add(label)
            ax.plot(fpr_c, tpr_c, color=c, linewidth=2, zorder=3, label=label)

    # ── v2.3：配对 DeLong 多模型 AUC 比较（--compare，需原始分数）──
    if kwargs.get("roc_compare") and _afstats is not None:
        labels_raw = data.get("labels", None)
        curves_cmp = data.get("curves", None)
        scores_ok = (labels_raw is not None and isinstance(curves_cmp, list)
                     and all("scores" in c for c in curves_cmp)
                     and len(curves_cmp) >= 2)
        if scores_ok:
            try:
                scores_by_model = {str(c.get("name", f"模型{i+1}")): c["scores"]
                                   for i, c in enumerate(curves_cmp)}
                aucs_d, pairs_d = _afstats.delong_paired(labels_raw, scores_by_model)
                lines = ["DeLong 配对检验"]
                for a_n, b_n, p_d, z_d in pairs_d:
                    lines.append(f"{a_n} vs {b_n}: p={p_d:.3g}")
                    print(f"  roc compare: {a_n} vs {b_n}: AUC "
                          f"{aucs_d[a_n]:.3f} vs {aucs_d[b_n]:.3f}, "
                          f"DeLong p={p_d:.4g} (z={z_d:.2g})", file=sys.stderr)
                ax.text(0.97, 0.32, "\n".join(lines), transform=ax.transAxes,
                        ha="right", va="top", fontsize=7, color="#333333",
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                                  alpha=0.92, edgecolor='lightgray'))
            except Exception as e:
                print(f"WARNING: roc: DeLong 计算失败（{e}）", file=sys.stderr)
        else:
            print("WARNING: roc: --compare 需要 labels（0/1 数组）+ 每条曲线含原始 "
                  "scores 数组（同一样本多模型）——只有 fpr/tpr 曲线时无法做 DeLong",
                  file=sys.stderr)

    # Diagonal reference line
    if diagonal:
        ax.plot([0, 1], [0, 1], '--', color='gray', alpha=0.5, linewidth=1, zorder=1)

    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_aspect('equal')
    ax.xaxis.grid(True, alpha=theme["grid_alpha"], linestyle='--')


def gen_stacked_bar(data, ax, theme, cjk_fp, **kwargs):
    """Stacked bar chart for compositional data (e.g., subgroup proportions)."""
    labels = data.get("labels", data.get("x", []))
    series = data.get("series", data.get("datasets", {}))
    percentage = data.get("percentage", False)  # normalize to 100%
    show_total = data.get("show_total", False)  # show total on top of each bar
    errors = data.get("errors", None)  # optional error bars for totals
    use_hatch = kwargs.get("hatch", False)

    n_groups = len(labels)
    x = np.arange(n_groups)
    colors = theme["colors"]
    bottoms = np.zeros(n_groups)

    for i, (name, values) in enumerate(series.items()):
        vals = np.array(values, dtype=float)
        c = colors[i % len(colors)]
        hatch_val = HATCH_PATTERNS[i % len(HATCH_PATTERNS)] if use_hatch else None
        bars = ax.bar(x, vals, 0.65, bottom=bottoms, color=c,
                      edgecolor=_hatch_edgecolor(theme, colors[i % len(colors)]) if use_hatch else 'white',
                      linewidth=0.6 if use_hatch else 0.5,
                      hatch=hatch_val, label=name, zorder=2)

        # Value labels inside bars (only for segments > 5% of total)
        totals = sum(np.array(s, dtype=float) for s in series.values())
        for j, (v, total) in enumerate(zip(vals, totals)):
            if total > 0 and v / total > 0.05:  # only label segments > 5%
                ax.text(x[j], bottoms[j] + v / 2, f'{v:.1f}' if not percentage else f'{v/total*100:.1f}%',
                        ha='center', va='center', fontsize=7, color='white', fontweight='bold',
                        zorder=3)

        bottoms += vals

    # Total labels on top
    if show_total:
        for j in range(n_groups):
            total = bottoms[j]
            ax.text(x[j], total + 0.5, f'N={total:.0f}', ha='center', va='bottom',
                    fontsize=7, color='#333333', fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=theme["font_size"] - 1,
                       fontproperties=cjk_fp if cjk_fp and any(has_cjk(l) for l in labels) else None)

    if percentage:
        ax.set_ylim(0, max(bottoms) * 1.1)


def _fmt_num(v):
    return f'{int(v)}' if float(v).is_integer() else f'{v:.1f}'


def _annotate_peak(ax, xs, labels, values, horizontal, theme, cjk_fp, series_name=None):
    """v4.2 --peak-label：最大值点自动注记（纯数据事实：峰值+所在类目）。"""
    vals = [float(v) for v in values]
    if len(vals) < 2:
        return
    im = int(max(range(len(vals)), key=lambda k: vals[k]))
    head = f"峰值 {_fmt_num(vals[im])}"
    lab = str(labels[im]) if im < len(labels) else ""
    txt = head + (f"（{lab}）" if lab else "") + (f" · {series_name}" if series_name else "")
    _px = xs[im] if isinstance(xs, (list, tuple)) and im < len(xs) else im
    ax.annotate(txt, xy=(_px, vals[im]) if not horizontal else (vals[im], im),
                xytext=(0, 14) if not horizontal else (14, 0),
                textcoords="offset points", ha="center" if not horizontal else "left",
                fontsize=max(6, theme["font_size"] - 0.5), color="#B3541E",
                fontproperties=cjk_fp if cjk_fp and has_cjk(txt) else None,
                arrowprops=dict(arrowstyle="-", color="#B3541E", lw=0.8), zorder=6)
    print(f"peak: {txt}", file=sys.stderr)


def gen_slope(data, ax, theme, cjk_fp, **kwargs):
    """Slope chart（v4.2，第 23 种图型）：两时点比较——每项一条左→右连线，
    两端直接标注"名称+数值"，最大上升项主题色强调、最大下降项暖橙。
    期刊 pre/post 标准形态（如治疗前后、基线→随访）。

    JSON: {"left_label": "基线", "right_label": "12 周",
           "items": {"药物A": [72, 85], "药物B": [65, 61]}}  # 每项恰好 2 个数值
    """
    items = data.get("items")
    if not isinstance(items, dict) or len(items) < 2:
        raise ValueError("slope: 需要 'items'（至少 2 项，每项 [左值, 右值]）")
    for n, v in items.items():
        if not (isinstance(v, (list, tuple)) and len(v) == 2
                and all(isinstance(x, (int, float)) for x in v)):
            raise ValueError(f"slope: items['{n}'] 必须是恰好 2 个数值 [左值, 右值]")
    names = list(items.keys())
    lv = [float(items[n][0]) for n in names]
    rv = [float(items[n][1]) for n in names]
    deltas = [r - l for l, r in zip(lv, rv)]
    i_rise = int(max(range(len(names)), key=lambda k: deltas[k]))
    i_fall = int(min(range(len(names)), key=lambda k: deltas[k]))

    from matplotlib.colors import to_rgba
    accent = theme["colors"][0]
    x0, x1 = 0.0, 1.0
    for i, n in enumerate(names):
        if i == i_rise and deltas[i_rise] > 0:
            c, lw, z = accent, 2.6, 3
        elif i == i_fall and deltas[i_fall] < 0:
            c, lw, z = "#D55E00", 2.2, 3
        else:
            c, lw, z = to_rgba(accent, 0.32), 1.5, 2
        ax.plot([x0, x1], [lv[i], rv[i]], color=c, lw=lw, zorder=z,
                marker="o", markersize=4, markerfacecolor=c)

    def _spread(vals):
        order = sorted(range(len(vals)), key=lambda k: vals[k])
        out = [0.0] * len(vals)
        lo, hi = min(vals), max(vals)
        gap = max((hi - lo) * 0.07, 1e-9)
        for a in range(1, len(order)):
            p, q = order[a - 1], order[a]
            out[q] = max(out[p] + gap, vals[q]) if vals[q] >= vals[p] else vals[q]
        # 自下而上推开后，若顶到底顺序错位再自上而下收一遍
        for a in range(len(order) - 2, -1, -1):
            p, q = order[a], order[a + 1]
            if out[q] - out[p] < gap:
                out[p] = out[q] - gap
        return out

    ly, ry = _spread(lv), _spread(rv)
    _fp = cjk_fp
    for i, n in enumerate(names):
        fp = _fp if _fp and has_cjk(n) else None
        ax.plot([x0], [lv[i]], "o", color=accent if i == i_rise else "#888888",
                markersize=4, zorder=3)
        ax.text(x0 - 0.04, ly[i], f"{n}  {_fmt_num(lv[i])}", ha="right", va="center",
                fontsize=theme["font_size"] - 0.5, color="#333333", fontproperties=fp)
        ax.text(x1 + 0.04, ry[i], f"{_fmt_num(rv[i])}  {n}", ha="left", va="center",
                fontsize=theme["font_size"] - 0.5, color="#333333", fontproperties=fp)

    ll = str(data.get("left_label", "") or "")
    rl = str(data.get("right_label", "") or "")
    ax.set_xlim(-0.6, 1.6)
    ax.set_xticks([x0, x1])
    ax.set_xticklabels([ll or "Before", rl or "After"],
                       fontsize=theme["font_size"], fontweight="bold",
                       fontproperties=_fp if _fp and (has_cjk(ll) or has_cjk(rl)) else None)
    _top = _fp if _fp and (has_cjk(ll) or has_cjk(rl)) else None
    if ll:
        ax.text(0, 1.03, ll, transform=ax.get_xaxis_transform(), ha="center",
                fontsize=theme["font_size"], fontweight="bold", color="#555555",
                fontproperties=_top)
    if rl:
        ax.text(1, 1.03, rl, transform=ax.get_xaxis_transform(), ha="center",
                fontsize=theme["font_size"], fontweight="bold", color="#555555",
                fontproperties=_top)
    apply_base_style(ax, theme)
    ax.grid(False)
    ax.set_yticks([])


def gen_volcano(data, ax, theme, cjk_fp, **kwargs):
    """Volcano plot（v4.4，第 24 种图型）：组学差异表达标准形态——
    x=log2(倍数变化)，y=-log10(p 值)；上调暖橙/下调蓝/非显著灰；
    阈值虚线（|log2FC| 与 p）+ 显著性 Top-N 自动名称标注（确定性偏移避让）。

    JSON: {"log2fc": [2.1, -1.3, ...], "pvalue": [1e-6, 0.03, ...],
           "names": ["GeneA", ...](可选), "fc_cut": 1.0, "p_cut": 0.05, "top": 10}
    """
    import math
    l2 = data.get("log2fc")
    pv = data.get("pvalue")
    if not (isinstance(l2, list) and isinstance(pv, list)) or not l2 or len(l2) != len(pv):
        raise ValueError("volcano: 需要 'log2fc' 与 'pvalue' 两个等长数值数组")
    names = data.get("names")
    if names is not None and (not isinstance(names, list) or len(names) != len(l2)):
        raise ValueError("volcano: 'names' 长度必须与 log2fc 一致")
    try:
        l2v = [float(v) for v in l2]
        pvv = [float(v) for v in pv]
    except (TypeError, ValueError):
        raise ValueError("volcano: log2fc/pvalue 必须全为数值")
    if any(p <= 0 or p > 1 for p in pvv):
        raise ValueError("volcano: pvalue 必须在 (0, 1] 区间（p=0 无法取对数，请用最小可表示值如 1e-300）")
    fc_cut = float(data.get("fc_cut", 1.0))
    p_cut = float(data.get("p_cut", 0.05))
    top_n = int(data.get("top", 10))
    if fc_cut <= 0 or not (0 < p_cut < 1) or top_n < 0:
        raise ValueError("volcano: fc_cut>0、0<p_cut<1、top≥0")

    yv = [-math.log10(p) for p in pvv]
    sig_cut = -math.log10(p_cut)
    cls = []
    for x, y in zip(l2v, yv):
        if x >= fc_cut and y >= sig_cut:
            cls.append("up")
        elif x <= -fc_cut and y >= sig_cut:
            cls.append("down")
        else:
            cls.append("ns")
    colors = {"up": "#D55E00", "down": "#0072B2", "ns": "#B8B8B8"}
    sizes = {"up": 16, "down": 16, "ns": 9}
    for c in ("ns", "down", "up"):  # 显著点后画（置顶）
        xs = [x for x, k in zip(l2v, cls) if k == c]
        ys = [y for y, k in zip(yv, cls) if k == c]
        ax.scatter(xs, ys, s=sizes[c], c=colors[c], alpha=0.85 if c != "ns" else 0.7,
                   linewidths=0, zorder=3 if c != "ns" else 2)

    # 阈值参考线
    ax.axvline(fc_cut, color="#999999", ls="--", lw=0.9, zorder=1)
    ax.axvline(-fc_cut, color="#999999", ls="--", lw=0.9, zorder=1)
    ax.axhline(sig_cut, color="#999999", ls="--", lw=0.9, zorder=1)

    # 显著性 Top-N 名称标注（按 p 升序 = y 降序，确定性交错偏移）
    import matplotlib.pyplot as plt  # noqa: F401
    idx_sig = [i for i, k in enumerate(cls) if k in ("up", "down")]
    idx_sig.sort(key=lambda i: yv[i], reverse=True)
    n_up = sum(1 for k in cls if k == "up")
    n_down = sum(1 for k in cls if k == "down")
    for rank, i in enumerate(idx_sig[:top_n]):
        if names is None:
            break
        dx = 5 if l2v[i] >= 0 else -5
        ax.annotate(str(names[i]), xy=(l2v[i], yv[i]),
                    xytext=(dx, 4 + (rank % 3) * 5), textcoords="offset points",
                    ha="left" if dx > 0 else "right",
                    fontsize=max(5.5, theme["font_size"] - 1),
                    color=colors[cls[i]],
                    fontproperties=cjk_fp if cjk_fp and has_cjk(str(names[i])) else None)

    # 计数事实框（纯计数，零推断）
    ax.text(0.02, 0.98, f"↑{n_up}  ↓{n_down}  ns {len(cls) - n_up - n_down}",
            transform=ax.transAxes, va="top", ha="left",
            fontsize=theme["font_size"], color="#555555",
            fontproperties=cjk_fp if cjk_fp and has_cjk("上调") else None)

    # 坐标轴语义（类型专属默认；CLI --xlabel/--ylabel 可覆盖）
    xl = str(data.get("x_label", "") or "log2 fold change")
    yl = str(data.get("y_label", "") or "-log10(p-value)")
    ax.set_xlabel(xl, fontsize=theme["font_size"],
                  fontproperties=cjk_fp if cjk_fp and has_cjk(xl) else None)
    ax.set_ylabel(yl, fontsize=theme["font_size"],
                  fontproperties=cjk_fp if cjk_fp and has_cjk(yl) else None)
    ax.set_xlim(min(l2v) - 0.3, max(l2v) + 0.3)
    apply_base_style(ax, theme)


def gen_dual_axis(data, ax, theme, cjk_fp, **kwargs):
    """Dual Y-axis chart, canonical 左柱右线 form (v3.10): left-axis series draw
    as BARS, right-axis series as dashed LINES — override per side with data keys
    left_type/right_type ("bar"|"line"). The merged legend covers BOTH axes and is
    drawn frameless inside a reserved top band so it never occludes peaks (v3.10
    A2/A4 修复); --legend-loc / --legend-outside still honored."""
    labels = data.get("labels", data.get("x", []))
    left_series = data.get("left", data.get("y1", {}))  # {"CRP (mg/L)": [5, 8, 12, ...]}
    right_series = data.get("right", data.get("y2", {}))  # {"DAS28": [3.2, 4.1, 5.6, ...]}
    left_errors = data.get("left_errors", data.get("y1_errors", {}))
    right_errors = data.get("right_errors", data.get("y2_errors", {}))
    left_ylabel = data.get("left_ylabel", "")
    right_ylabel = data.get("right_ylabel", "")
    left_type = str(data.get("left_type", "bar")).strip().lower()
    right_type = str(data.get("right_type", "line")).strip().lower()
    if left_type not in ("bar", "line"):
        left_type = "bar"
    if right_type not in ("bar", "line"):
        right_type = "line"

    def _check_series_dict(sd, which):
        if not isinstance(sd, dict):
            raise ValueError(f"dual_axis: {which} must be a dict of {{series_name: [values]}}")
        for k, v in sd.items():
            if not isinstance(v, (list, tuple)) or not all(isinstance(x, (int, float)) for x in v):
                raise ValueError(
                    f"dual_axis: {which}['{k}'] must be a numeric list. "
                    f"Wrong format? Use {{\"{which}\": {{\"系列名\": [值, ...]}}}} — not "
                    f"{{\"name\": ..., \"values\": ...}}.")
    _check_series_dict(left_series, "left")
    _check_series_dict(right_series, "right")

    markers = ['o', 's', 'D', '^', 'v', 'p', '*', 'h']
    x = np.arange(len(labels)) if not any(isinstance(l, (int, float)) for l in labels) else np.array(labels, dtype=float)

    # Create second axis
    ax2 = ax.twinx()

    # Plot left axis series（v3.10：默认柱状——经典左柱右线形态）
    n_left = len(left_series)
    n_right = len(right_series)
    _label_all = (n_left + n_right) > 1  # 唯一系列不设 label（图例抑制）
    if left_type == "bar":
        w_left = 0.72 / max(n_left, 1)
        for i, (name, values) in enumerate(left_series.items()):
            c = theme["colors"][i % len(theme["colors"])]
            offs = (i - (n_left - 1) / 2) * w_left
            errs = left_errors.get(name) or None
            if errs is not None and not all(isinstance(e, (int, float)) for e in errs):
                errs = None
            ax.bar(x + offs, values, w_left * 0.9, yerr=errs,
                   color=c, edgecolor='white', linewidth=0.5, capsize=3,
                   error_kw={'linewidth': 1},
                   label=name if _label_all else None, zorder=2.5)
    else:
        for i, (name, values) in enumerate(left_series.items()):
            c = theme["colors"][i % len(theme["colors"])]
            mk = markers[i % len(markers)]
            ax.plot(x, values, color=c, marker=mk, markersize=6, linewidth=2,
                    label=name if _label_all else None, zorder=3)
            if name in left_errors and left_errors[name]:
                errs = left_errors[name]
                lower = [v - e for v, e in zip(values, errs)]
                upper = [v + e for v, e in zip(values, errs)]
                ax.fill_between(x, lower, upper, color=c, alpha=0.15, zorder=2)

    # Plot right axis series
    right_colors = ['#D55E00', '#CC79A7', '#0072B2', '#009E73', '#F0E442']  # distinct from left
    if theme.get("colorblind_safe"):
        # Use different Okabe-Ito colors for right axis
        offset = len(left_series)
        right_colors = [theme["colors"][(offset + j) % len(theme["colors"])] for j in range(5)]

    if right_type == "bar":
        w_right = 0.72 / max(n_right, 1)
        for i, (name, values) in enumerate(right_series.items()):
            c = right_colors[i % len(right_colors)]
            offs = (i - (n_right - 1) / 2) * w_right
            errs = right_errors.get(name) or None
            if errs is not None and not all(isinstance(e, (int, float)) for e in errs):
                errs = None
            ax2.bar(x + offs, values, w_right * 0.9, yerr=errs,
                    color=c, edgecolor='white', linewidth=0.5, capsize=3,
                    error_kw={'linewidth': 1},
                    label=name if _label_all else None, zorder=2.5)
    else:
        for i, (name, values) in enumerate(right_series.items()):
            c = right_colors[i % len(right_colors)]
            mk = markers[(n_left + i) % len(markers)]
            ax2.plot(x, values, color=c, marker=mk, markersize=6, linewidth=2,
                     linestyle='--', label=name if _label_all else None, zorder=3)
            if name in right_errors and right_errors[name]:
                errs = right_errors[name]
                lower = [v - e for v, e in zip(values, errs)]
                upper = [v + e for v, e in zip(values, errs)]
                ax2.fill_between(x, lower, upper, color=c, alpha=0.15, zorder=2)

    # Style right axis
    ax2.spines['right'].set_visible(True)
    ax2.tick_params(axis='y', labelsize=theme["font_size"] - 1)
    ax2.grid(False)  # no grid on right axis

    # Set x-axis labels
    if not any(isinstance(l, (int, float)) for l in labels):
        ax.set_xticks(x)
        use_cjk = cjk_fp and any(has_cjk(l) for l in labels)
        ax.set_xticklabels(labels, fontsize=theme["font_size"] - 1,
                           fontproperties=cjk_fp if use_cjk else None)

    # Axis labels
    if left_ylabel:
        ax.set_ylabel(left_ylabel, fontsize=theme["font_size"],
                      fontproperties=cjk_fp if cjk_fp and has_cjk(left_ylabel) else None)
        _ensure_ylabel_clear(ax)
    if right_ylabel:
        ax2.set_ylabel(right_ylabel, fontsize=theme["font_size"],
                       fontproperties=cjk_fp if cjk_fp and has_cjk(right_ylabel) else None)
        _ensure_ylabel_clear(ax2)

    # Combine legends from both axes（v3.10 A2/A4：显式合并+不遮挡）
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    handles, lbls = lines1 + lines2, labels1 + labels2
    # v3.10：可选轴下限覆盖（如 right_floor=35 让百分比右轴整数起算——投稿规范；默认保持 5% 边距）
    for _key, _ax in (("left_floor", ax), ("right_floor", ax2)):
        _fl = data.get(_key)
        if isinstance(_fl, (int, float)) and not isinstance(_fl, bool):
            _lo, _hi = _ax.get_ylim()
            if _fl < _hi:
                _ax.set_ylim(float(_fl), _hi)
            else:
                print(f"WARNING: dual_axis {_key}={_fl} 不小于当前上限 {_hi:.4g}，已忽略",
                      file=sys.stderr)
    if handles:
        if kwargs.get("legend_outside"):
            ax.legend(handles, lbls, fontsize=theme["font_size"] - 1,
                      loc='lower center', bbox_to_anchor=(0.5, 1.02),
                      ncol=min(len(lbls), 4), frameon=False,
                      prop=cjk_fp if cjk_fp else None)
        elif kwargs.get("legend_loc"):
            ax.legend(handles, lbls, fontsize=theme["font_size"] - 1,
                      loc=kwargs["legend_loc"], framealpha=0.9,
                      prop=cjk_fp if cjk_fp else None)
        else:
            # 默认：左右轴各留顶部预留带，图例嵌入预留区（无边框，物理不遮数据）
            for _a in (ax, ax2):
                _lo, _hi = _a.get_ylim()
                if _hi > _lo:
                    _a.set_ylim(_lo, _hi + (_hi - _lo) * (0.18 if len(lbls) <= 4 else 0.28))
            ax.legend(handles, lbls, fontsize=theme["font_size"] - 1,
                      loc='upper center', ncol=min(len(lbls), 4), frameon=False,
                      prop=cjk_fp if cjk_fp else None)

    # Store ax2 reference for downstream use
    return ax2


def gen_composite(data, ax, theme, cjk_fp, **kwargs):
    """Multi-panel composite figure (e.g., Panel A + B + C for journal figures).

    JSON format:
    {
      "layout": [rows, cols],  // e.g. [1, 3] or [2, 2]
      "panels": [
        {
          "title": "Panel A: ...",
          "type": "bar",        // any chart type from GENERATORS
          "data": { ... },      // data for that chart type
          "xlabel": "...", "ylabel": "...",
          "pos": [row, col]     // grid position (0-indexed)
        },
        ...
      ]
    }
    """
    import matplotlib.gridspec as gridspec

    layout = data.get("layout", [1, 2])
    n_rows, n_cols = layout[0], layout[1]
    panels = data.get("panels", [])

    if not panels:
        return None

    fig = ax.figure
    # Clear the default axis created by plt.subplots
    ax.remove()

    gs = gridspec.GridSpec(n_rows, n_cols, figure=fig,
                           hspace=0.35, wspace=0.3,
                           left=0.08, right=0.95, top=0.92, bottom=0.08)

    # v4.1 自动面板标签（期刊 A/B/C 规范自动化）："panel_labels": true → 按
    # pos 行序自动加粗 A/B/C…；传数组（如 ["I","II"]）自定义序列；缺省 false
    # （兼容既有图，避免与手写 "Panel A:" 类标题重复标注）。
    panel_labels = data.get("panel_labels", False)
    _pl_seq = panel_labels if isinstance(panel_labels, list) else None
    _pl_on = bool(panel_labels)
    _pos_order = sorted(range(len(panels)),
                        key=lambda i: (panels[i].get("pos", [9, 9])[0],
                                       panels[i].get("pos", [9, 9])[1]))
    _pl_of = {idx: k for k, idx in enumerate(_pos_order)}

    for _pi, panel in enumerate(panels):
        pos = panel.get("pos", [0, 0])
        panel_type = panel.get("type", "bar")
        panel_data = panel.get("data", {})

        _rs, _cs = panel.get("span", [1, 1]) or [1, 1]
        try:
            _rs, _cs = int(_rs), int(_cs)
        except (TypeError, ValueError):
            _rs = _cs = 1
        _rs = max(1, min(_rs, n_rows - pos[0]))
        _cs = max(1, min(_cs, n_cols - pos[1]))
        sub_ax = fig.add_subplot(gs[pos[0]:pos[0] + _rs, pos[1]:pos[1] + _cs])

        # Get the generator function
        gen_func = GENERATORS.get(panel_type)
        if gen_func is None:
            sub_ax.text(0.5, 0.5, f"Unknown type: {panel_type}",
                        ha='center', va='center', transform=sub_ax.transAxes)
            continue

        # Pass through relevant kwargs
        panel_kwargs = {
            "show_values": panel.get("show_values", kwargs.get("show_values", False)),
            "trend": panel.get("trend", kwargs.get("trend", True)),
            # B3(v2.7)：hbar/horizontal_bar 面板自动横排（与主入口同规则；实战坑：composite
            # 内 hbar 被当竖 bar 渲染，用户被迫改用 bar+horizontal 绕行）
            "horizontal": panel.get("horizontal", False)
                          or panel_type in ("hbar", "horizontal_bar"),
            "hatch": panel.get("hatch", False),
            "alternate": panel.get("alternate", False),
            "show_ratio": panel.get("show_ratio", False),
            "cmap": panel.get("cmap", kwargs.get("cmap")),
            "vmin": panel.get("vmin", kwargs.get("vmin")),
            # v3.4.1（55 线发现+82 等效移植）：KM 面板 median_auto 面板级透传——
            # 此前白名单缺失，composite 里 median_auto:false 被静默忽略（单位错标复发）
            "median_auto": panel.get("median_auto", kwargs.get("median_auto", True)),
            "stats_bootstrap": panel.get("stats_bootstrap", kwargs.get("stats_bootstrap", False)),
            "direct_label": panel.get("direct_label", kwargs.get("direct_label", False)),
            "vmax": panel.get("vmax", kwargs.get("vmax")),
        }

        extra = gen_func(panel_data, sub_ax, theme, cjk_fp, **panel_kwargs)
        apply_base_style(sub_ax, theme)

        # v4.1 自动面板标签：左上角加粗 A/B/C…（轴外，永不压数据）
        if _pl_on:
            _lab = (_pl_seq[_pl_of[_pi]] if _pl_seq
                    else chr(65 + _pl_of[_pi]))
            sub_ax.text(-0.08, 1.05, str(_lab), transform=sub_ax.transAxes,
                        fontsize=theme["font_size"] + 3, fontweight="bold",
                        ha="right", va="bottom",
                        fontproperties=cjk_fp if cjk_fp and has_cjk(str(_lab)) else None)

        # Panel-specific labels
        ptitle = panel.get("title", "")
        if ptitle:
            sub_ax.set_title(ptitle, fontsize=theme["font_size"], fontweight='bold', pad=8,
                             fontproperties=cjk_fp if cjk_fp and has_cjk(ptitle) else None)
        if panel.get("xlabel"):
            sub_ax.set_xlabel(panel["xlabel"], fontsize=theme["font_size"] - 1,
                              fontproperties=cjk_fp if cjk_fp and has_cjk(panel["xlabel"]) else None)
        if panel.get("ylabel"):
            sub_ax.set_ylabel(panel["ylabel"], fontsize=theme["font_size"] - 1,
                              fontproperties=cjk_fp if cjk_fp and has_cjk(panel["ylabel"]) else None)
            _ensure_ylabel_clear(sub_ax)

        # Legend for panel
        show_legend = panel.get("legend", True)
        if show_legend and sub_ax.get_legend_handles_labels()[1]:
            sub_ax.legend(fontsize=theme["font_size"] - 2, loc='best', framealpha=0.9,
                          prop=cjk_fp if cjk_fp else None)

        # Colorbar for heatmap panels
        if extra is not None and hasattr(extra, 'get_cmap'):
            cbar = fig.colorbar(extra, ax=sub_ax, shrink=0.8)

    return "composite"  # signal to main() that figure is already built


def gen_diagram(data, ax, theme, cjk_fp, **kwargs):
    """Architecture/flow diagram with colored blocks, arrows, and groupings.

    JSON format:
    {
      "background": "light",  // always light (white) for publication
      "blocks": [
        {"id": "A", "label": "Input", "x": 0, "y": 0, "w": 2, "h": 1,
         "color": "#56B4E9", "shape": "round"},  // shape: "round" (default) or "rect"
        ...
      ],
      "arrows": [
        {"from": "A", "to": "B", "label": "flow", "style": "->"},
        ...
      ],
      "groups": [
        {"blocks": ["A", "B"], "label": "Phase 1", "color": "#009E73", "style": "dashed"},
        ...
      ],
      "annotations": [
        {"text": "Step 1: predict", "x": 1, "y": -1, "fontsize": 9, "color": "#E69F00"},
        ...
      ]
    }
    """
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
    from matplotlib.lines import Line2D

    blocks = data.get("blocks", [])
    arrows = data.get("arrows", [])
    groups = data.get("groups", [])
    annotations = data.get("annotations", [])
    bg = data.get("background", "light")

    text_color = '#1a1a1a'
    arrow_color = '#555555'

    # Build block lookup
    block_map = {}
    for b in blocks:
        block_map[b["id"]] = b

    # Draw group backgrounds first (behind blocks)
    for grp in groups:
        grp_blocks = grp.get("blocks", [])
        if not grp_blocks:
            continue
        # Calculate bounding box of grouped blocks
        xs_min, xs_max = [], []
        ys_min, ys_max = [], []
        for bid in grp_blocks:
            if bid in block_map:
                b = block_map[bid]
                xs_min.append(b["x"])
                xs_max.append(b["x"] + b["w"])
                ys_min.append(b["y"])
                ys_max.append(b["y"] + b["h"])
        if not xs_min:
            continue
        pad = 0.3
        gx, gy = min(xs_min) - pad, min(ys_min) - pad
        gw, gh = max(xs_max) - min(xs_min) + 2 * pad, max(ys_max) - min(ys_min) + 2 * pad
        grp_color = grp.get("color", "#888888")
        grp_style = grp.get("style", "dashed")
        rect = Rectangle((gx, gy), gw, gh, linewidth=2,
                         edgecolor=grp_color, facecolor='none',
                         linestyle=grp_style, alpha=0.8)
        ax.add_patch(rect)
        # Group label
        if grp.get("label"):
            ax.text(gx + 0.15, gy + gh - 0.15, grp["label"],
                    fontsize=theme["font_size"] - 1, color=grp_color,
                    fontweight='bold', va='top', ha='left',
                    fontproperties=cjk_fp if cjk_fp and has_cjk(grp["label"]) else None)

    # Draw blocks
    for b in blocks:
        bx, by = b["x"], b["y"]
        bw, bh = b["w"], b["h"]
        bc = b.get("color", theme["colors"][0])
        label = b.get("label", b["id"])
        shape = b.get("shape", "round")
        sub_label = b.get("sublabel", None)  # smaller text below main label

        if shape == "rect":
            patch = FancyBboxPatch((bx, by), bw, bh,
                                   boxstyle="square,pad=0",
                                   facecolor=bc, edgecolor=bc,
                                   linewidth=1.5, alpha=0.85)
        else:
            patch = FancyBboxPatch((bx, by), bw, bh,
                                   boxstyle="round,pad=0.1",
                                   facecolor=bc, edgecolor='white',
                                   linewidth=1.2, alpha=0.9)
        ax.add_patch(patch)

        # Block label (centered)
        label_y = by + bh / 2
        if sub_label:
            label_y = by + bh * 0.65
        ax.text(bx + bw / 2, label_y, label,
                ha='center', va='center', fontsize=theme["font_size"],
                color='white', fontweight='bold',
                fontproperties=cjk_fp if cjk_fp and has_cjk(label) else None)
        if sub_label:
            ax.text(bx + bw / 2, by + bh * 0.3, sub_label,
                    ha='center', va='center', fontsize=theme["font_size"] - 2,
                    color='white', alpha=0.85,
                    fontproperties=cjk_fp if cjk_fp and has_cjk(sub_label) else None)

    # Draw arrows
    for arr in arrows:
        from_id = arr["from"]
        to_id = arr["to"]
        if from_id not in block_map or to_id not in block_map:
            continue
        fb, tb = block_map[from_id], block_map[to_id]

        # Calculate connection points (edge of blocks facing each other)
        fx_center = fb["x"] + fb["w"] / 2
        fy_center = fb["y"] + fb["h"] / 2
        tx_center = tb["x"] + tb["w"] / 2
        ty_center = tb["y"] + tb["h"] / 2

        # Determine arrow start/end at block edges
        if abs(fx_center - tx_center) > abs(fy_center - ty_center):
            # Horizontal connection
            if fx_center < tx_center:
                start = (fb["x"] + fb["w"], fy_center)
                end = (tb["x"], ty_center)
            else:
                start = (fb["x"], fy_center)
                end = (tb["x"] + tb["w"], ty_center)
        else:
            # Vertical connection
            if fy_center < ty_center:
                start = (fx_center, fb["y"] + fb["h"])
                end = (tx_center, tb["y"])
            else:
                start = (fx_center, fb["y"])
                end = (tx_center, tb["y"] + tb["h"])

        arr_style = arr.get("style", "->")
        arr_color = arr.get("color", arrow_color)
        connection_style = f"arc3,rad={arr.get('rad', 0)}"

        arrow = FancyArrowPatch(start, end,
                                arrowstyle=arr_style,
                                connectionstyle=connection_style,
                                color=arr_color, linewidth=1.5,
                                mutation_scale=15)
        ax.add_patch(arrow)

        # Arrow label
        if arr.get("label"):
            mid_x = (start[0] + end[0]) / 2
            mid_y = (start[1] + end[1]) / 2
            ax.text(mid_x, mid_y + 0.15, arr["label"],
                    ha='center', va='bottom', fontsize=theme["font_size"] - 2,
                    color=text_color,
                    bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                              alpha=0.8, edgecolor='none'),
                    fontproperties=cjk_fp if cjk_fp and has_cjk(arr["label"]) else None)

    # Draw annotations
    for ann in annotations:
        ax.text(ann["x"], ann["y"], ann["text"],
                ha=ann.get("ha", 'center'), va=ann.get("va", 'center'),
                fontsize=ann.get("fontsize", theme["font_size"]),
                color=ann.get("color", text_color),
                fontweight=ann.get("weight", 'normal'),
                fontproperties=cjk_fp if cjk_fp and has_cjk(ann["text"]) else None)

    # Set up axis limits
    all_x = [b["x"] + b["w"] for b in blocks] + [b["x"] for b in blocks]
    all_y = [b["y"] + b["h"] for b in blocks] + [b["y"] for b in blocks]
    if all_x and all_y:
        ax.set_xlim(min(all_x) - 1, max(all_x) + 1)
        ax.set_ylim(min(all_y) - 1.5, max(all_y) + 1.5)

    ax.set_aspect('equal')
    ax.axis('off')

    return "diagram"


# ── PRISMA 2020 flow diagram (v2.1) ───────────────────────────────────

PRISMA_LABELS = {
    "en": {
        "identification": "Identification", "screening": "Screening", "included": "Included",
        "identified": "Records identified from\ndatabases",
        "duplicates": "Records removed before\nscreening (duplicates)",
        "screened": "Records screened",
        "excluded": "Records excluded",
        "sought": "Reports sought for\nretrieval",
        "not_retrieved": "Reports not retrieved",
        "assessed": "Reports assessed for\neligibility",
        "reasons": "Reports excluded:",
        "included_box": "Studies included in\nreview",
    },
    "zh": {
        "identification": "识别", "screening": "筛选", "included": "纳入",
        "identified": "数据库检索获得的\n记录",
        "duplicates": "初筛前剔除的记录\n（重复文献）",
        "screened": "初筛的记录",
        "excluded": "初筛排除",
        "sought": "寻求获取的报告",
        "not_retrieved": "未能获取的报告",
        "assessed": "进行合格性评估\n的报告",
        "reasons": "排除的报告：",
        "included_box": "纳入综述的研究",
    },
}


def gen_prisma(data, ax, theme, cjk_fp, **kwargs):
    """PRISMA 2020 systematic-review flow diagram.

    JSON format (counts must add up; validate_data() gates arithmetic):
    {
      "records_identified": 128,       // required
      "duplicates_removed": 23,
      "records_screened": 105,         // default: identified - duplicates
      "records_excluded": 61,
      "reports_sought": 44,            // default: screened - excluded
      "reports_not_retrieved": 3,
      "reports_assessed": 41,          // default: sought - not_retrieved
      "exclusion_reasons": {"Wrong population": 5, "Wrong intervention": 7},
      "studies_included": 25,          // required
      "lang": "en"                     // or "zh" (standard Chinese wording)
    }
    Layout: PRISMA 2020 three-phase spine (Identification / Screening /
    Included) with exclusion boxes to the right, per the official template.
    """
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

    lang = data.get("lang", "en")
    L = PRISMA_LABELS.get(lang, PRISMA_LABELS["en"])

    def _n(key):
        v = data.get(key)
        return v if isinstance(v, int) and not isinstance(v, bool) else 0

    identified = _n("records_identified")
    dup = _n("duplicates_removed")
    screened = data.get("records_screened")
    screened = (identified - dup) if not isinstance(screened, int) else screened
    excluded = _n("records_excluded")
    sought = data.get("reports_sought")
    sought = (screened - excluded) if not isinstance(sought, int) else sought
    not_ret = _n("reports_not_retrieved")
    assessed = data.get("reports_assessed")
    assessed = (sought - not_ret) if not isinstance(assessed, int) else assessed
    reasons = data.get("exclusion_reasons") or {}
    included = _n("studies_included")

    spine_color = theme["colors"][0]
    final_color = theme["colors"][1] if len(theme["colors"]) > 1 else spine_color
    side_face, side_edge, text_color = "#F2F2F2", "#8A8A8A", "#1a1a1a"
    arrow_color = "#555555"
    fs = theme["font_size"]

    def _fp(*texts):
        return cjk_fp if cjk_fp and any(has_cjk(t) for t in texts) else None

    # ── geometry (data units; aspect equal) ──
    SW, BW = 4.6, 4.4                 # spine / side box widths
    SX, XX = 0.0, 7.4                 # x origins
    GAP = 0.78                        # vertical gap
    n_reasons = max(1, len(reasons))
    # 内容感知盒高：双行中文标签+计数行在固定盒高下会溢出框体——
    # 盒高 = 标签行数×行高 + 计数行 + 内边距，行高随字号缩放
    _lh = 0.62 * max(0.8, fs / 8.0)
    def _box_h(label):
        return max(1.15, (label.count(chr(10)) + 1) * _lh + 0.85)
    BH_BY = {n: _box_h(L["included_box"] if n == "included" else L[n])
             for n in ("identified", "screened", "sought", "assessed", "included")}
    BH = max(BH_BY.values())
    RH = max(BH, 0.95 + 0.42 * n_reasons * max(0.8, fs / 8.0))

    order = ["identified", "screened", "sought", "assessed", "included"]
    ys = {}
    top = 10.0
    y = top
    for name in order:
        ys[name] = y - BH_BY[name]
        y -= (BH_BY[name] + GAP)

    def _cy(name):
        return ys[name] + BH / 2

    side = {
        "duplicates": (ys["identified"] + ys["screened"]) / 2 + BH / 2 - BH,
        "excluded": (ys["screened"] + ys["sought"]) / 2 + BH / 2 - BH,
        "not_retrieved": (ys["sought"] + ys["assessed"]) / 2 + BH / 2 - BH,
    }
    show_dup = not (dup == 0 and "duplicates_removed" not in data)
    show_notret = not (not_ret == 0 and "reports_not_retrieved" not in data)
    # reasons box: top-anchored to the assessed row's midline, growing
    # downward — this leaves the sought/assessed slot free for the
    # not-retrieved side box (official PRISMA 2020 arrangement)
    y_reasons = ys["assessed"] + BH_BY["assessed"] * 0.5 - RH
    implied_excluded = max(assessed - included, 0)

    # ── limits (set early so side-box text can be measured in data units) ──
    xmin, ymin = SX - 2.3, min(ys["included"], y_reasons) - 1.1
    ymax = top + 0.75
    ax.set_xlim(xmin, XX + BW + 0.5)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.axis("off")
    fig = ax.get_figure()
    # 主框文字实测自愈：盒高系数是估算可能低估——以最终几何实测文字高度，
    # 超出盒体就放大该盒并整体重排，迭代到全部装下（同侧框 auto-fit 思路）
    if fig is not None:
        for _round in range(4):
            fig.canvas.draw()
            _rend = fig.canvas.get_renderer()
            _inv = ax.transData.inverted()
            grew = False
            for _name in order:
                _label = L["included_box"] if _name == "included" else L[_name]
                _t = ax.text(0.5, 0.5, _label + "\n" + "n = 000",
                             fontsize=fs - 1, fontweight="bold",
                             fontproperties=_fp(_label))
                _need = _t.get_window_extent(renderer=_rend).transformed(_inv).height + 0.30
                _t.remove()
                if _need > BH_BY[_name] * 1.02:
                    BH_BY[_name] = _need
                    grew = True
            if not grew:
                break
            BH = max(BH_BY.values())
            RH = max(RH, BH)
            _y = top
            for _name in order:
                ys[_name] = _y - BH_BY[_name]
                _y -= (BH_BY[_name] + GAP)
            y_reasons = ys["assessed"] + BH_BY["assessed"] * 0.5 - RH
            ymin = min(ys["included"], y_reasons) - 1.1
            ax.set_ylim(ymin, ymax)


    # ── side-box auto-fit: measure the real rendered width of every side-box
    # line, widen the boxes to fit, and wrap reason lines only as a last
    # resort (growing the box height to match). The old fixed-width box let
    # long exclusion reasons spill outside the frame.
    BW_MAX = 7.2
    reason_items = [(str(r), n) for r, n in reasons.items()]
    item_display = {r: [f"· {r} (n = {n})"] for r, n in reason_items}
    specs = []
    if show_dup:
        specs.append((L["duplicates"], fs - 1, _fp(L["duplicates"])))
    specs.append((L["excluded"], fs - 1, _fp(L["excluded"])))
    if show_notret:
        specs.append((L["not_retrieved"], fs - 1, _fp(L["not_retrieved"])))
    specs.append((L["reasons"], fs - 1, _fp(L["reasons"])))
    for r, n in reason_items:
        specs.append((item_display[r][0], fs - 1.5, _fp(r, str(n))))

    if specs and fig is not None:
        # Iterate to a fixed point: set the final geometry FIRST, then
        # measure, because data-unit widths depend on xlim. Widening BW
        # changes the span, which changes the measurement — so each pass
        # measures under the span it proposes, until the width stops moving.
        widths = {}
        need = BW
        for _pass in range(3):
            ax.set_xlim(xmin, XX + BW + 0.5)
            ax.set_ylim(ymin, ymax)
            meas = [ax.text(XX + BW / 2, (ymin + ymax) / 2, txt, fontsize=fsize,
                            fontproperties=fp, alpha=0, zorder=-10)
                    for txt, fsize, fp in specs]
            fig.canvas.draw()
            ren = fig.canvas.get_renderer()
            inv = ax.transData.inverted()
            widths = {}
            for t, (txt, _f, _p) in zip(meas, specs):
                bb = t.get_window_extent(ren)
                widths[txt] = abs(inv.transform((bb.x1, bb.y1))[0]
                                  - inv.transform((bb.x0, bb.y0))[0])
                t.remove()
            need = max(widths.values()) + 0.7 if widths else BW
            BW_new = min(max(BW, need), BW_MAX)
            if BW_new == BW:
                break
            BW = BW_new
        if need > BW_MAX:
            import textwrap

            def _block_w(block, fsize, fp):
                t = ax.text(XX + BW / 2, (ymin + ymax) / 2, block, fontsize=fsize,
                            fontproperties=fp, alpha=0, zorder=-10)
                fig.canvas.draw()
                bb = t.get_window_extent(fig.canvas.get_renderer())
                t.remove()
                return abs(inv.transform((bb.x1, bb.y1))[0]
                           - inv.transform((bb.x0, bb.y0))[0])

            for r, n in reason_items:
                line = item_display[r][0]
                if widths.get(line, 0) + 0.7 > BW_MAX:
                    per = max(8, int(len(line) * (BW_MAX - 0.7) / max(widths[line], 1e-6)))
                    for _attempt in range(4):
                        wrapped = textwrap.wrap(line, per) or [line]
                        display = [wrapped[0]] + ["   " + s for s in wrapped[1:]]
                        if _block_w("\n".join(display), fs - 1.5,
                                    _fp(r, str(n))) + 0.7 <= BW_MAX:
                            break
                        per = max(6, int(per * 0.8))
                    item_display[r] = display
            extra = sum(len(v) - 1 for v in item_display.values())
            RH += 0.30 * extra
            y_reasons = ys["assessed"] + BH_BY["assessed"] * 0.5 - RH
        ymin = min(ys["included"], y_reasons) - 1.1
        ax.set_xlim(xmin, XX + BW + 0.5)
        ax.set_ylim(ymin, ymax)

    # grow two-line side boxes vertically if label + count overflow BH
    # (a wider canvas squeezes data-unit heights). Boxes grow symmetrically
    # around their center, so the arrow anchors (_scy) stay aligned.
    side_two = []
    if show_dup:
        side_two.append(("duplicates", L["duplicates"]))
    side_two.append(("excluded", L["excluded"]))
    if show_notret:
        side_two.append(("not_retrieved", L["not_retrieved"]))
    side_h = {k: BH for k, _ in side_two}
    if fig is not None:
        fig.canvas.draw()
        _ren = fig.canvas.get_renderer()
        _inv = ax.transData.inverted()

        def _text_h(text, fsize, fp):
            t = ax.text(XX + BW / 2, (ymin + ymax) / 2, text, fontsize=fsize,
                        fontproperties=fp, alpha=0, zorder=-10)
            fig.canvas.draw()
            bb = t.get_window_extent(fig.canvas.get_renderer())
            t.remove()
            return abs(_inv.transform((0, bb.y1))[1] - _inv.transform((0, bb.y0))[1])

        for key, lab in side_two:
            need = (_text_h(lab, fs - 1, _fp(lab))
                    + _text_h("n = 0", fs - 1.5, _fp("0")) + 0.52)
            side_h[key] = max(BH, need)

    # phase bands + rotated phase labels (canonical three-phase template,
    # left-rail style: zero collision with the vertical flow)
    phases = [("identification", ["identified"]),
              ("screening", ["screened", "sought", "assessed"]),
              ("included", ["included"])]
    for label, rows in phases:
        y0 = min(ys[r] for r in rows) - 0.42
        y1 = max(ys[r] + BH for r in rows) + 0.42
        ax.add_patch(FancyBboxPatch((SX - 0.45, y0), SW + 0.9, y1 - y0,
                                    boxstyle="round,pad=0.05", facecolor=spine_color,
                                    edgecolor="none", alpha=0.06, zorder=0))
        ax.text(SX - 0.95, (y0 + y1) / 2, L[label], ha="center", va="center",
                rotation=90, fontsize=fs, color="#555555", fontweight="bold",
                fontproperties=_fp(L[label]))

    def _main_box(name, label, count, color=None):
        c = color or spine_color
        _bh = BH_BY[name]
        ax.add_patch(FancyBboxPatch((SX, ys[name]), SW, _bh, boxstyle="round,pad=0.08",
                                    facecolor=c, edgecolor="white", linewidth=1.2,
                                    alpha=0.95, zorder=3))
        ax.text(SX + SW / 2, ys[name] + _bh * 0.68, label, ha="center", va="center",
                fontsize=fs - 1, color="white", fontweight="bold",
                fontproperties=_fp(label))
        ax.text(SX + SW / 2, ys[name] + _bh * 0.22, f"n = {count}", ha="center",
                va="center", fontsize=fs - 1.5, color="white",
                fontproperties=_fp(str(count)))

    def _side_box(y0, h, lines, counts=None):
        ax.add_patch(FancyBboxPatch((XX, y0), BW, h, boxstyle="round,pad=0.08",
                                    facecolor=side_face, edgecolor=side_edge,
                                    linewidth=1.0, zorder=3))
        if counts is None:
            label, count = lines
            ax.text(XX + BW / 2, y0 + h * 0.63, label, ha="center", va="center",
                    fontsize=fs - 1, color=text_color, fontproperties=_fp(label))
            ax.text(XX + BW / 2, y0 + h * 0.26, f"n = {count}", ha="center", va="center",
                    fontsize=fs - 1.5, color=text_color, fontproperties=_fp(str(count)))
        else:
            title, items = lines, counts
            ax.text(XX + BW / 2, y0 + h - 0.34, title, ha="center", va="center",
                    fontsize=fs - 1, color=text_color, fontweight="bold",
                    fontproperties=_fp(title))
            n_rows = sum(txt.count("\n") + 1 for txt, _ in items)
            step = (h - 0.62) / max(1, n_rows)
            yy = y0 + h - 0.34 - step
            for txt, n in items:
                ax.text(XX + BW / 2, yy, txt, ha="center", va="center",
                        fontsize=fs - 1.5, color=text_color,
                        fontproperties=_fp(str(n)))
                yy -= step * (txt.count("\n") + 1)

    def _arrow(x0, y0, x1, y1, lw=1.6):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="->",
                                     color=arrow_color, linewidth=lw,
                                     mutation_scale=14, zorder=2))

    # spine boxes + arrows
    _main_box("identified", L["identified"], identified)
    _main_box("screened", L["screened"], screened)
    _main_box("sought", L["sought"], sought)
    _main_box("assessed", L["assessed"], assessed)
    _main_box("included", L["included_box"], included, color=final_color)
    for a, b in zip(order, order[1:]):
        _arrow(SX + SW / 2, ys[a], SX + SW / 2, ys[b] + BH)

    # side boxes + arrows
    def _scy(key):
        return side[key] + BH / 2

    if show_dup:
        h = side_h["duplicates"]
        _side_box(side["duplicates"] + BH / 2 - h / 2, h, (L["duplicates"], dup))
        _arrow(SX + SW, _scy("duplicates"), XX, _scy("duplicates"), lw=1.4)
    h = side_h["excluded"]
    _side_box(side["excluded"] + BH / 2 - h / 2, h, (L["excluded"], excluded))
    _arrow(SX + SW, _scy("excluded"), XX, _scy("excluded"), lw=1.4)
    if show_notret:
        h = side_h["not_retrieved"]
        _side_box(side["not_retrieved"] + BH / 2 - h / 2, h, (L["not_retrieved"], not_ret))
        _arrow(SX + SW, _scy("not_retrieved"), XX, _scy("not_retrieved"), lw=1.4)
    if reasons:
        items = [("\n".join(item_display[r]), n) for r, n in reason_items]
        _side_box(y_reasons, RH, L["reasons"], items)
    else:
        _side_box(y_reasons, BH, (L["reasons"], implied_excluded))
    _arrow(SX + SW, ys["assessed"] + BH_BY["assessed"] * 0.35, XX, ys["assessed"] + BH_BY["assessed"] * 0.35, lw=1.4)

    # content-aware figure proportions (limits were set pre-draw for the
    # side-box auto-fit; BW/y_reasons carry the auto-fitted values)
    xmax = XX + BW + 0.5
    ymin = min(ys["included"], y_reasons) - 1.1
    if fig is not None:
        span_h, span_w = ymax - ymin, xmax - xmin
        fig_w = fig.get_size_inches()[0]
        fig.set_size_inches(fig_w, max(4.0, fig_w * (span_h / span_w) * 0.92))

    return "diagram"



GENERATORS = {
    "bar": gen_bar,
    "grouped_bar": gen_bar,
    "hbar": gen_bar,
    "horizontal_bar": gen_bar,
    "stacked_bar": gen_stacked_bar,
    "heatmap": gen_heatmap,
    "scatter": gen_scatter,
    "line": gen_line,
    "dual_axis": gen_dual_axis,
    "box": gen_box,
    "boxplot": gen_box,
    "forest": gen_forest,
    "km": gen_km,
    "survival": gen_km,
    "roc": gen_roc,
    "violin": gen_violin,
    "composite": gen_composite,
    "diagram": gen_diagram,
    "prisma": gen_prisma,
    "slope": gen_slope,
    "volcano": gen_volcano,
}
