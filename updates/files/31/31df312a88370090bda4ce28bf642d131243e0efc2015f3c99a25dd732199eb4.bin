#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2.3 新图型模块：funnel / bland_altman / pca / paired / venn / cluster_heatmap。

由 gen_figure.py 在启动时 import 并合并进 GENERATORS/DEMO_DATA；
校验与 alt 文本经 validate_extra()/alt_extra() 钩子接入。
仅依赖 numpy + matplotlib + af_v23_stats。
"""
from __future__ import annotations

import sys

import numpy as np

try:
    import af_v23_stats as st
except ImportError:  # 同目录运行时直接可用；打包路径异常时显式报错
    raise

MAX_CLUSTER_ROWS = 3000   # linkage O(n²) 内存护栏
MAX_PCA_COLS = 200        # 特征列护栏


def _has_cjk(text):
    if not isinstance(text, str):
        return False
    return any('\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f'
               for ch in text)


def _fp(cjk_fp, text):
    return cjk_fp if (cjk_fp is not None and _has_cjk(str(text))) else None


def _warn(msg):
    print(f"WARNING: {msg}", file=sys.stderr)


# ── funnel 漏斗图 ─────────────────────────────────────────────────────

def gen_funnel(data, ax, theme, cjk_fp, **kwargs):
    """Meta 分析漏斗图：研究效应散点 + 合并效应竖线 + 95% 伪置信漏斗线。

    数据: {"studies": [{"name": "Smith 2020", "effect": 0.69, "se": 0.12}, ...]}
    或 {"effects": [...], "ses": [...], "labels": [...] }（效应建议为 log 尺度）。
    选项: egger=True 画 Egger 回归线（stderr 报告不对称检验 p）。
    """
    studies = data.get("studies", None)
    if studies:
        names = [str(s.get("name", f"研究{i+1}")) for i, s in enumerate(studies)]
        es = [float(s["effect"]) for s in studies]
        ses = [float(s["se"]) for s in studies]
    else:
        es = data.get("effects", data.get("effects_list", None))
        ses = data.get("ses", data.get("se_list", None))
        names = list(data.get("labels", []))
        if es is None or ses is None:
            raise ValueError(
                "funnel: 需要 'studies'（每项含 name/effect/se）或 'effects'+'ses' 数组 — "
                "森林图的 effect/lci/uci 格式请先换算（se≈(uci−lci)/3.92）")
    if len(es) != len(ses) or len(es) == 0:
        raise ValueError(f"funnel: effects({len(es)}) 与 ses({len(ses)}) 数量不一致或为空")
    es = np.asarray(es, float)
    ses = np.asarray(ses, float)
    bad = ~(np.isfinite(es) & np.isfinite(ses) & (ses > 0))
    if bad.any():
        raise ValueError(f"funnel: {int(bad.sum())} 个研究的 se 非法（必须为正且有限）")
    if len(es) < 5:
        _warn(f"funnel: 仅 {len(es)} 个研究，漏斗对称性目测不可靠（建议 >=10）")

    pooled = st.dl_pool(es, ses)
    c_main = theme["colors"][0]

    ax.scatter(es, ses, s=36, color=c_main, edgecolor="#333333",
               linewidth=0.8, zorder=4)
    se_max = float(ses.max()) * 1.08
    se_min = 0.0
    # 95% 伪置信漏斗
    for sign in (-1.0, 1.0):
        ax.plot([pooled["pooled"] - 1.96 * se_max, pooled["pooled"],
                 pooled["pooled"] + 1.96 * se_max],
                [se_max, se_min, se_max],
                color="#888888", linewidth=1.2, linestyle="--", zorder=2)
    ax.axvline(pooled["pooled"], color=c_main, linewidth=1.4, linestyle="-",
               alpha=0.85, zorder=3,
               label=f"合并效应 {pooled['pooled']:.3g}")
    ax.axvline(0, color="#BBBBBB", linewidth=0.8, zorder=1)
    ax.invert_yaxis()
    ax.set_ylabel("标准误 se")
    ax.set_xlabel("效应值")

    if kwargs.get("egger"):
        if len(es) >= 3:
            eg = st.egger_test(es, ses)
            # Egger 线：z = intercept + slope * (1/se) → effect = intercept*se + slope
            se_grid = np.linspace(se_min, se_max, 32)
            ax.plot(eg["slope"] + eg["intercept"] * se_grid, se_grid,
                    color=theme["colors"][1 % len(theme["colors"])],
                    linewidth=1.2, linestyle=":", zorder=3,
                    label=f"Egger 回归线 (P={eg['p']:.3g})")
            _warn(f"funnel: Egger 不对称检验 P={eg['p']:.4g}（截距 {eg['intercept']:.3g}）")
        else:
            _warn("funnel: Egger 检验需要 >=3 个研究，已跳过")
    ax.legend(fontsize=theme["font_size"] - 1, loc="upper right", framealpha=0.9,
              prop=cjk_fp if _has_cjk("".join(names)) or cjk_fp and _has_cjk(str(data.get("title", ""))) else None)
    _warn(f"funnel: DL 随机效应合并 {pooled['pooled']:.4g}（95%CI {pooled['pooled']-1.96*pooled['se']:.3g}~"
          f"{pooled['pooled']+1.96*pooled['se']:.3g}），异质性 I²={pooled['i2']:.0f}%，P_het={pooled['p_het']:.3g}")
    return None


# ── bland_altman 一致性分析 ───────────────────────────────────────────

def gen_bland_altman(data, ax, theme, cjk_fp, **kwargs):
    """Bland-Altman 一致性图：均值差 vs 均值，LoA=mean±1.96SD。

    数据: {"a": [...], "b": [...]} 或 {"methods": {"新方法": [...], "金标准": [...]}}
    （methods 恰好两项，差值=第一项−第二项）。
    """
    a, b, name_a, name_b = _two_series(data, "bland_altman")
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    if len(a) != len(b) or len(a) < 3:
        raise ValueError(f"bland_altman: 两组数据须等长且 >=3 对（当前 {len(a)} vs {len(b)}）")
    if np.any(~np.isfinite(a)) or np.any(~np.isfinite(b)):
        raise ValueError("bland_altman: 含非数值/NaN")
    mean_ab = (a + b) / 2.0
    diff = a - b
    md = float(np.mean(diff))
    sd = float(np.std(diff, ddof=1))
    loa_hi, loa_lo = md + 1.96 * sd, md - 1.96 * sd

    ax.scatter(mean_ab, diff, s=34, color=theme["colors"][0],
               edgecolor="#333333", linewidth=0.8, zorder=4)
    ax.axhline(md, color=theme["colors"][1 % len(theme["colors"])], lw=1.4, zorder=3,
               label=f"均值差 {md:.3g}")
    for v, tag in ((loa_hi, "+1.96SD"), (loa_lo, "−1.96SD")):
        ax.axhline(v, color="#888888", lw=1.2, linestyle="--", zorder=3,
                   label=f"{tag} {v:.3g}")
    ax.axhline(0, color="#CCCCCC", lw=0.8, zorder=2)
    ax.set_xlabel(f"两法均值 ({name_a}/{name_b})")
    ax.set_ylabel(f"差值 ({name_a}−{name_b})")
    ax.legend(fontsize=theme["font_size"] - 1, loc="best", framealpha=0.9,
              prop=_fp(cjk_fp, name_a + name_b))
    _warn(f"bland_altman: 一致性界值 [{loa_lo:.3g}, {loa_hi:.3g}]，"
          f"差值均值 {md:.3g}（SD {sd:.3g}），n={len(a)}")
    return None


def _two_series(data, chart_name):
    """取恰好两个系列：支持 {'a':..,'b':..} 或 {'methods': {名:.., 名:..}}。"""
    if "a" in data and "b" in data:
        return data["a"], data["b"], str(data.get("label_a", "A")), str(data.get("label_b", "B"))
    methods = data.get("methods", None)
    if isinstance(methods, dict) and len(methods) == 2:
        (na, va), (nb, vb) = methods.items()
        return va, vb, str(na), str(nb)
    raise ValueError(
        f"{chart_name}: 需要 'a'+'b' 数组，或 'methods' 恰好两个系列 "
        f"（如 {{\"新方法\": [...], \"金标准\": [...]}}）")



def _declutter_texts(ax, texts, anchors, max_pass=120, step=9.0,
                     max_disp_frac=0.15, leader_min_frac=0.02):
    """散点数据标签防重叠：重叠排斥 + 锚点弹簧 + 位移上限 + 引导线。

    - 排斥：测量真实 bbox，重叠对互推（显示坐标测量、数据坐标移动）
    - 锚点弹簧：每轮向自己的数据点回拉，标签永不远离锚点
    - 位移上限：标签离锚点超过 max_disp_frac·min(轴跨度) 即强制拉回边界
    - 引导线：最终位移 > leader_min_frac 时画点→标签细线，保证对应关系可读
    返回剩余重叠对数。
    """
    if len(texts) < 2:
        return 0
    import math as _m
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    inv = ax.transData.inverted()
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    span = min(x1 - x0, y1 - y0)
    max_disp = max_disp_frac * span
    leader_min = leader_min_frac * span
    for _pass in range(max_pass):
        bbs = [t.get_window_extent(renderer) for t in texts]
        n_over = 0
        moves = [(0.0, 0.0)] * len(texts)
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                bi, bj = bbs[i], bbs[j]
                if bi.x1 < bj.x0 or bj.x1 < bi.x0 or bi.y1 < bj.y0 or bj.y1 < bi.y0:
                    continue
                n_over += 1
                dx = (bi.x0 + bi.x1) / 2 - (bj.x0 + bj.x1) / 2
                dy = (bi.y0 + bi.y1) / 2 - (bj.y0 + bj.y1) / 2
                dist = _m.hypot(dx, dy) or 1.0
                ux, uy = dx / dist, dy / dist
                if abs(dx) < 0.5 and abs(dy) < 0.5:
                    ang = 2.399 * (i + 1)
                    ux, uy = _m.cos(ang), _m.sin(ang)
                moves[i] = (moves[i][0] + ux * step, moves[i][1] + uy * step)
                moves[j] = (moves[j][0] - ux * step, moves[j][1] - uy * step)
        if n_over == 0:
            break
        p0 = inv.transform((0, 0))
        p1 = inv.transform((step, step))
        ddx, ddy = p1[0] - p0[0], p1[1] - p0[1]
        for t, (mx, my), (axn, ayn) in zip(texts, moves, anchors):
            tx, ty = t.get_position()
            nx, ny = tx + mx * ddx, ty + my * ddy
            nx += (axn - nx) * 0.25   # 锚点弹簧
            ny += (ayn - ny) * 0.25
            ddx_a, ddy_a = nx - axn, ny - ayn
            dist_a = _m.hypot(ddx_a, ddy_a)
            if dist_a > max_disp:     # 位移上限：拉回锚点邻域
                nx = axn + ddx_a / dist_a * max_disp
                ny = ayn + ddy_a / dist_a * max_disp
            t.set_position((nx, ny))
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
    bbs = [t.get_window_extent(renderer) for t in texts]
    n_over = 0
    for i in range(len(bbs)):
        for j in range(i + 1, len(bbs)):
            if bbs[i].overlaps(bbs[j]):
                n_over += 1
    # 引导线：位移超阈值的标签画点→标签细线（对应关系可读）
    drawn = 0
    for t, (axn, ayn) in zip(texts, anchors):
        tx, ty = t.get_position()
        if _m.hypot(tx - axn, ty - ayn) > leader_min:
            ax.plot([axn, tx], [ayn, ty], color="#AAAAAA", linewidth=0.7,
                    zorder=5, clip_on=False)
            drawn += 1
    return n_over


def _thin_overlapping_texts(ax, texts):
    """最后手段：反复移除卷入重叠最多的标签，直到无重叠。返回移除数（调用方发 stderr 警告）。"""
    fig = ax.figure
    removed = 0
    while texts:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        bbs = [t.get_window_extent(renderer) for t in texts]
        worst, worst_n = -1, 0
        for i, bi in enumerate(bbs):
            n = sum(1 for j, bj in enumerate(bbs) if j != i and bi.overlaps(bj))
            if n > worst_n:
                worst, worst_n = i, n
        if worst_n == 0:
            break
        texts[worst].remove()
        texts.pop(worst)
        removed += 1
    return removed


# ── pca 得分图 ────────────────────────────────────────────────────────

def gen_pca(data, ax, theme, cjk_fp, **kwargs):
    """PCA 得分图（PC1×PC2）：标准化默认开，分组椭圆=均值±2SD，载荷 top5。

    数据: {"matrix": [[...]], "row_labels": [...], "groups": [...](可选, 按行),
           "feature_names": [...]}
    """
    matrix = data.get("matrix", data.get("values", None))
    if matrix is None or not isinstance(matrix, (list, tuple)) or len(matrix) == 0:
        raise ValueError("pca: 需要 'matrix'（二维数值数组，行=样本 列=特征）")
    X = np.asarray(matrix, dtype=float)
    if X.ndim != 2 or X.shape[0] < 3:
        raise ValueError(f"pca: 矩阵需 >=3 行样本（当前 {X.shape}）")
    if X.shape[1] < 2:
        raise ValueError("pca: 至少 2 个特征列")
    if X.shape[1] > MAX_PCA_COLS:
        raise ValueError(f"pca: 特征列 {X.shape[1]} 超过上限 {MAX_PCA_COLS}（维度过高请先降维/筛选）")
    if np.any(~np.isfinite(X)):
        raise ValueError("pca: 矩阵含 NaN/Inf——请先补全或剔除")
    row_labels = list(data.get("row_labels", data.get("labels", [])))
    groups = data.get("groups", None)
    feature_names = list(data.get("feature_names", [f"特征{i+1}" for i in range(X.shape[1])]))
    if len(feature_names) != X.shape[1]:
        print(f"WARNING: pca feature_names 数量（{len(feature_names)}）与变量数"
              f"（{X.shape[1]}）不符，已自动改用默认名 特征1..{X.shape[1]}", file=sys.stderr)
        feature_names = [f"特征{i+1}" for i in range(X.shape[1])]

    scale = kwargs.get("scale", True)
    Xc = X - X.mean(axis=0)
    if scale:
        sd = X.std(axis=0, ddof=1)
        if np.any(sd == 0):
            zero_cols = int(np.sum(sd == 0))
            keep = sd > 0
            Xc = Xc[:, keep]
            feature_names = [f for f, k in zip(feature_names, keep) if k]
            _warn(f"pca: {zero_cols} 个零方差特征列已剔除")
            if Xc.shape[1] < 2:
                raise ValueError("pca: 剔除零方差列后不足 2 列")
        Xc = Xc / Xc.std(axis=0, ddof=1)
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    scores = U * S
    total_var = float(np.sum(S ** 2))
    var_pct = [S[i] ** 2 / total_var * 100 for i in range(min(2, len(S)))]

    import math as _m
    label_texts = []
    _anchors = []
    if groups and isinstance(groups, (list, tuple)) and len(groups) == X.shape[0]:
        uniq = list(dict.fromkeys(str(g) for g in groups))
        for gi, g in enumerate(uniq):
            mask = np.array([str(x) == g for x in groups])
            pts = scores[mask, :2]
            c = theme["colors"][gi % len(theme["colors"])]
            ax.scatter(pts[:, 0], pts[:, 1], s=36, color=c, edgecolor="#333333",
                       linewidth=0.8, zorder=4, label=str(g))
            if mask.sum() >= 3:
                mu = pts.mean(axis=0)
                sd_pts = pts.std(axis=0, ddof=1)
                theta = np.linspace(0, 2 * np.pi, 72)
                ell = np.c_[mu[0] + 2 * sd_pts[0] * np.cos(theta),
                            mu[1] + 2 * sd_pts[1] * np.sin(theta)]
                ax.plot(ell[:, 0], ell[:, 1], color=c, linewidth=1.1,
                        alpha=0.65, linestyle="--", zorder=3)
    else:
        ax.scatter(scores[:, 0], scores[:, 1], s=36, color=theme["colors"][0],
                   edgecolor="#333333", linewidth=0.8, zorder=4)
        if 0 < len(row_labels) == X.shape[0] and X.shape[0] <= 40:
            _fs = max(6, theme["font_size"] - 2)
            _sx = float(np.ptp(scores[:, 0])) or 1.0
            _sy = float(np.ptp(scores[:, 1])) or 1.0
            _anchors = []
            for i, rl in enumerate(row_labels):
                ang = 2.399 * i  # 黄金角环绕初始位，天然散开减少推移
                ox, oy = _sx * 0.02 * _m.cos(ang), _sy * 0.02 * _m.sin(ang)
                label_texts.append(ax.text(
                    scores[i, 0] + ox, scores[i, 1] + oy,
                    str(rl), fontsize=_fs, color="#555555",
                    fontproperties=_fp(cjk_fp, rl), zorder=6,
                    ha="center", va="center"))
                _anchors.append((scores[i, 0], scores[i, 1]))

    # 载荷箭头 top5（|PC1|+|PC2|）
    loadings = Vt[:2, :].T
    imp = np.abs(loadings).sum(axis=1)
    top_idx = np.argsort(imp)[::-1][:5]
    scale_l = np.abs(scores[:, :2]).max() * 0.42 / max(imp[top_idx].max(), 1e-12)
    import matplotlib.patches as _mpatches
    _sx = float(np.ptp(scores[:, 0])) or 1.0
    _sy = float(np.ptp(scores[:, 1])) or 1.0
    for idx in top_idx:
        lx, ly = loadings[idx, 0] * scale_l, loadings[idx, 1] * scale_l
        ax.add_patch(_mpatches.FancyArrowPatch(
            (0, 0), (lx, ly), arrowstyle="->", mutation_scale=14,
            color="#E8A33D", lw=1.3, zorder=5, shrinkA=0, shrinkB=0))
        label_texts.append(ax.text(
            lx + _sx * 0.012, ly + _sy * 0.012, feature_names[idx],
            fontsize=max(6, theme["font_size"] - 2), color="#8a6414",
            fontproperties=_fp(cjk_fp, feature_names[idx]), zorder=7,
            ha="left", va="bottom"))
        _anchors.append((lx, ly))
    ax.axhline(0, color="#CCCCCC", lw=0.8, zorder=1)
    ax.axvline(0, color="#CCCCCC", lw=0.8, zorder=1)
    ax.set_xlabel(f"PC1（解释 {var_pct[0]:.1f}%）")
    ax.set_ylabel(f"PC2（解释 {var_pct[1]:.1f}%）")
    if groups:
        ax.legend(fontsize=theme["font_size"] - 1, loc="best", framealpha=0.9,
                  prop=_fp(cjk_fp, " ".join(str(g) for g in groups)))
    ax.update_datalim(scores[:, :2])
    ax.autoscale_view()
    if label_texts:
        n_left = _declutter_texts(ax, label_texts, _anchors)
        if n_left > 0:
            removed = _thin_overlapping_texts(ax, label_texts)
            if removed:
                _warn(f"pca: 样本标签过密，已省略 {removed} 个重叠标签"
                      "（完整样本清单见 --alt 无障碍描述）")
    _warn(f"pca: PC1+PC2 累计解释 {var_pct[0]+var_pct[1]:.1f}% 方差"
          f"（标准化={'是' if scale else '否'}）")
    return None


# ── paired 配对前后图 ─────────────────────────────────────────────────

def gen_paired(data, ax, theme, cjk_fp, **kwargs):
    """配对前后折线图：每个受试对象一条线 + 配对检验（配对 t / Wilcoxon 符号秩）。

    数据: {"before": [...], "after": [...]} 或
          {"series": {"术前": [...], "术后": [...]}}（恰好两项）+ 可选 labels。
    """
    from scipy import stats as _st
    if "before" in data and "after" in data:
        a = list(data["before"]); b = list(data["after"])
        name_a, name_b = str(data.get("label_a", "Before")), str(data.get("label_b", "After"))
    else:
        series = data.get("series", None)
        if not (isinstance(series, dict) and len(series) == 2):
            raise ValueError(
                "paired: 需要 'before'+'after' 数组，或 'series' 恰好两项"
                "（如 {\"术前\": [...], \"术后\": [...]}）")
        (name_a, a), (name_b, b) = series.items()
    a = np.asarray(a, float); b = np.asarray(b, float)
    if len(a) != len(b) or len(a) < 2:
        raise ValueError(f"paired: 两组须等长且 >=2 对（当前 {len(a)} vs {len(b)}）")
    if np.any(~np.isfinite(a)) or np.any(~np.isfinite(b)):
        raise ValueError("paired: 含非数值/NaN")

    n = len(a)
    c_a = theme["colors"][0]; c_b = theme["colors"][1 % len(theme["colors"])]
    for i in range(n):
        ax.plot([0, 1], [a[i], b[i]], color="#B9B9B9", lw=1.1, zorder=2,
                marker="o", markersize=4, markerfacecolor="white",
                markeredgecolor="#777777")
    ax.scatter(np.zeros(n), a, s=42, color=c_a, edgecolor="#333333",
               linewidth=0.8, zorder=4, label=name_a)
    ax.scatter(np.ones(n), b, s=42, color=c_b, edgecolor="#333333",
               linewidth=0.8, zorder=4, label=name_b)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([name_a, name_b],
                       fontproperties=_fp(cjk_fp, name_a + name_b))
    ax.set_xlim(-0.35, 1.35)

    if kwargs.get("stats_auto"):
        d = b - a
        use_t = True
        if 3 <= n <= 5000 and float(_st.shapiro(d).pvalue) <= 0.05:
            use_t = False
        if n >= 6 and use_t:
            _, p = _st.ttest_rel(b, a)
            method = "配对 t 检验"
        elif n >= 6:
            _, p = _st.wilcoxon(b, a)
            method = "Wilcoxon 符号秩"
        else:
            _warn(f"paired: n={n} <6，检验效力不足，未做统计标注")
            p, method = None, ""
        if p is not None:
            stars = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "n.s."
            top = float(max(a.max(), b.max()))
            span = max(abs(top) * 0.08, 1e-9)
            yi = top + span
            ax.plot([0, 0, 1, 1], [yi - span * 0.25, yi, yi, yi - span * 0.25],
                    color="#333333", lw=1.2, zorder=6)
            ax.text(0.5, yi + span * 0.08, stars, ha="center", va="bottom",
                    fontsize=max(7, theme["font_size"]), color="#333333", zorder=6)
            ax.set_ylim(top=yi + span * 0.7)
            _warn(f"paired: {name_b} vs {name_a}：{method}，p={p:.4g} → {stars}")
    ax.set_ylabel("测量值")
    ax.legend(fontsize=theme["font_size"] - 1, loc="best", framealpha=0.9,
              prop=_fp(cjk_fp, name_a + name_b))
    return None


# ── venn 韦恩图 ───────────────────────────────────────────────────────

# ── venn 面积比例（Euler）几何求解 ────────────────────────────────────

def _circle_overlap_area(d, r1, r2):
    """两圆交集面积（d=圆心距）。d>=r1+r2 → 0；d<=|r1-r2| → 较小圆全面积。"""
    import math as _m
    if d >= r1 + r2:
        return 0.0
    r_min = min(r1, r2)
    if d <= abs(r1 - r2):
        return _m.pi * r_min * r_min
    a1 = r1 * r1 * _m.acos((d * d + r1 * r1 - r2 * r2) / (2 * d * r1))
    a2 = r2 * r2 * _m.acos((d * d + r2 * r2 - r1 * r1) / (2 * d * r2))
    a3 = 0.5 * _m.sqrt(max(0.0, (-d + r1 + r2) * (d + r1 - r2)
                                * (d - r1 + r2) * (d + r1 + r2)))
    return a1 + a2 - a3


_R_MIN = 0.04  # 空集/极小集合仍可辨识的最小视觉半径（0-1 归一坐标）


def _fit_into_unit(centers, radii, margin=0.16):
    """把布局（任意单位）平移缩放到 [0,1]² 内切（留 margin 给集合名标签）。
    返回 (centers, radii, affine)，affine=(cx, cy, s) 供质心同批换算。"""
    xs = [c[0] for c in centers]
    ys = [c[1] for c in centers]
    x0, x1 = min(xs) - max(radii), max(xs) + max(radii)
    y0, y1 = min(ys) - max(radii), max(ys) + max(radii)
    span = max(x1 - x0, y1 - y0) or 1.0
    s = (1.0 - 2 * margin) / span
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    out_c = [((c[0] - cx) * s + 0.5, (c[1] - cy) * s + 0.5) for c in centers]
    return out_c, [r * s for r in radii], (cx, cy, s)


def _venn2_geometry(n1, n2, inter):
    """2 集合 Euler 布局（解析解）。n1=|A\\B|, n2=|B\\A|, inter=|A∩B|（计数）。

    返回 (centers, radii, notes)：notes 为需 stderr 提示的异常布局说明列表。"""
    import math as _m
    from scipy.optimize import brentq
    t1, t2 = n1 + inter, n2 + inter
    if inter > t1 or inter > t2:
        raise ValueError("venn --area: 区域计数不自洽——交集计数不能大于任一集合的总数"
                         f"（当前交={inter}，两集合总={t1}/{t2}）")
    notes = []
    if t1 <= 0 and t2 <= 0:
        return [(0.40, 0.50), (0.60, 0.50)], [_R_MIN, _R_MIN], ["两个集合均为空"]
    r1 = _m.sqrt(t1 / _m.pi) if t1 > 0 else None
    r2 = _m.sqrt(t2 / _m.pi) if t2 > 0 else None
    if inter <= 0:
        # 不相交（或单侧为空）：留 12% 间隙并列
        if t1 <= 0:
            notes.append("集合 A 为空（图中以最小圆示意）")
        if t2 <= 0:
            notes.append("集合 B 为空（图中以最小圆示意）")
        rr1 = max(r1 if t1 > 0 else 0.0, 0.0)
        rr2 = max(r2 if t2 > 0 else 0.0, 0.0)
        d = (rr1 + rr2) * 1.12
        centers, radii, _aff = _fit_into_unit([(-d / 2, 0.0), (d / 2, 0.0)], [rr1, rr2])
        return centers, radii, notes
    if n1 <= 0 and n2 <= 0:
        # 两集合完全相同：同心微偏，仍能看出两层边
        r = _m.sqrt(t1 / _m.pi)
        centers, radii, _aff = _fit_into_unit([(0.0, 0.0), (0.0, 0.0)], [r, r])
        radii[1] = radii[0] * 0.985
        notes.append("两集合元素完全相同（同心绘制）")
        return centers, radii, notes
    if n1 <= 0 or n2 <= 0:
        # 单侧包含：A ⊆ B（或反向），内切
        if n1 <= 0:
            r_in, r_out = r1, r2
        else:
            r_in, r_out = r2, r1
        d = r_out - r_in
        centers, radii, _aff = _fit_into_unit([(0.0, 0.0), (d, 0.0)], [r_out, r_in])
        if n1 <= 0:
            centers = centers[::-1]
            radii = radii[::-1]
        notes.append("子集关系：小集合完全包含于大集合")
        return centers, radii, notes
    # 常规：半径固定，brentq 解圆心距 d 使交集面积=inter（面积单位=计数）
    lo, hi = abs(r1 - r2) * (1 + 1e-9), (r1 + r2) * (1 - 1e-9)
    f = lambda d: _circle_overlap_area(d, r1, r2) - inter
    if f(lo) < 0:      # inter 达到包含上限（计数不自洽的边界）
        d = lo
    elif f(hi) > 0:    # inter 小于相切下限（几乎不相交）
        d = hi
    else:
        d = brentq(f, lo, hi, xtol=1e-10, rtol=1e-12)
    centers, radii, _aff = _fit_into_unit([(0.0, 0.0), (d, 0.0)], [r1, r2])
    return centers, radii, notes


def _venn_region_masks(centers, radii, box, res):
    """网格化各区域（2 或 3 圆），返回 (area dict, centroid dict, cell_area)。
    box=(x0,y0,x1,y1)；area 以坐标面积为单位；centroid 为数据坐标（空区域为 None）。
    键：单集 "1"/"2"[/"3"]、两两 "12"…、三集 "123"。"""
    xs = np.linspace(box[0], box[2], res)
    ys = np.linspace(box[1], box[3], res)
    X, Y = np.meshgrid(xs, ys)
    cell = (box[2] - box[0]) * (box[3] - box[1]) / (res * res)
    ins = [(X - c[0]) ** 2 + (Y - c[1]) ** 2 <= r * r for c, r in zip(centers, radii)]
    if len(ins) == 2:
        a, b = ins
        masks = {"1": a & ~b, "2": b & ~a, "12": a & b}
    else:
        a, b, c = ins
        masks = {"1": a & ~b & ~c, "2": b & ~a & ~c, "3": c & ~a & ~b,
                 "12": a & b & ~c, "13": a & c & ~b, "23": b & c & ~a,
                 "123": a & b & c}
    areas, cents = {}, {}
    for k, m in masks.items():
        n = int(m.sum())
        areas[k] = n * cell
        cents[k] = (float(X[m].mean()), float(Y[m].mean())) if n else None
    return areas, cents, cell


def _triple_overlap_area(c1, c2, c3, r1, r2, r3, n=2048):
    """三圆交集面积：竖弦长 1D 积分（凸集 → 截面交集=交集截面，无网格噪声）。
    L(x) = max(0, min(上弦) − max(下弦))，逐圆弦在圆外时长度取 0。"""
    cxs = (c1[0], c2[0], c3[0])
    cys = (c1[1], c2[1], c3[1])
    rs = (r1, r2, r3)
    x0 = max(cx - r for cx, r in zip(cxs, rs))
    x1 = min(cx + r for cx, r in zip(cxs, rs))
    if x1 <= x0:
        return 0.0
    xs = np.linspace(x0, x1, n)
    los, his = [], []
    for cx, cy, r in zip(cxs, cys, rs):
        dx2 = np.clip(r * r - (xs - cx) ** 2, 0.0, None)
        s = np.sqrt(dx2)
        los.append(cy - s)
        his.append(cy + s)
    lower = np.maximum.reduce(los)
    upper = np.minimum.reduce(his)
    L = np.clip(upper - lower, 0.0, None)
    return float(np.sum((L[1:] + L[:-1]) * 0.5 * np.diff(xs)))


def _venn3_geometry(regions, keys):
    """3 集合 Euler 布局：半径由集合总数定，圆心按区域计数拟合。

    目标函数 6/7 项解析（成对交集闭式解 + 容斥单集），仅三集合项用小网格，
    避免纯网格分段常数导致的 trust-region 早停；初值=成对解析解三角布置。
    regions 键：k1/k2/k3/k1k2/k1k3/k2k3/k1k2k3（计数）。
    返回 (centers, radii, fit)；fit 含 max_rel_err（非零区域最大面积相对偏差）。
    """
    import math as _m
    from scipy.optimize import least_squares, brentq
    k1, k2, k3 = keys
    idx = {k1: "1", k2: "2", k3: "3", k1 + k2: "12", k1 + k3: "13",
           k2 + k3: "23", k1 + k2 + k3: "123"}
    target = {v: float(regions[k]) for k, v in idx.items()}
    totals = [target["1"] + target["12"] + target["13"] + target["123"],
              target["2"] + target["12"] + target["23"] + target["123"],
              target["3"] + target["13"] + target["23"] + target["123"]]
    radii_ideal = [_m.sqrt(t / _m.pi) if t > 0 else 1e-3 for t in totals]

    def _pair_d(i, j, ov):
        """解析解两圆心距使交集面积=ov；不可行时夹到边界。"""
        ri, rj = radii_ideal[i], radii_ideal[j]
        lo, hi = abs(ri - rj) * (1 + 1e-9), (ri + rj) * (1 - 1e-9)
        f = lambda d: _circle_overlap_area(d, ri, rj) - ov
        if ov <= 0:
            return hi + (ri + rj) * 0.12
        if f(lo) < 0:
            return lo
        if f(hi) > 0:
            return hi
        return brentq(f, lo, hi, xtol=1e-10, rtol=1e-12)

    # 初值：成对交集 = 两两区域 + 三集合，解析求三个圆心距 → 三角布置
    d12 = _pair_d(0, 1, target["12"] + target["123"])
    d13 = _pair_d(0, 2, target["13"] + target["123"])
    d23 = _pair_d(1, 2, target["23"] + target["123"])

    def regions_from_centers(centers, radii):
        c1, c2, c3 = centers
        ov12 = _circle_overlap_area(_m.hypot(c1[0] - c2[0], c1[1] - c2[1]),
                                    radii[0], radii[1])
        ov13 = _circle_overlap_area(_m.hypot(c1[0] - c3[0], c1[1] - c3[1]),
                                    radii[0], radii[2])
        ov23 = _circle_overlap_area(_m.hypot(c2[0] - c3[0], c2[1] - c3[1]),
                                    radii[1], radii[2])
        tri = _triple_overlap_area(c1, c2, c3, radii[0], radii[1], radii[2])
        only1 = _m.pi * radii[0] ** 2 - ov12 - ov13 + tri
        only2 = _m.pi * radii[1] ** 2 - ov12 - ov23 + tri
        only3 = _m.pi * radii[2] ** 2 - ov13 - ov23 + tri
        return [only1, only2, only3, ov12 - tri, ov13 - tri, ov23 - tri, tri]

    # 圆心 + 半径联合拟合（venneuler 思路）：固定半径的圆无法精确实现任意
    # 7 区域面积（数学上常无解），放开半径 + 锚定惩罚项可把误差压到低个位数 %
    _rad_w = 0.35

    def residuals(p):
        centers = [(p[0], p[1]), (p[2], p[3]), (p[4], p[5])]
        radii = [p[6], p[7], p[8]]
        got = regions_from_centers(centers, radii)
        res = [(g - t) / max(t, 1.0)
               for g, t in zip(got, target.values())]
        res += [_rad_w * (r - ri) / ri
                for r, ri in zip(radii, radii_ideal)]
        return res

    # 多起点（成对解析三角布置 / 嵌套堆叠 / 等边对称），各自两段精修，取代价最小者
    r_max0 = max(radii_ideal)
    cos_a = (d12 * d12 + d13 * d13 - d23 * d23) / (2 * d12 * d13)
    cos_a = max(-1.0, min(1.0, cos_a))
    tri_pt = (d13 * cos_a, d13 * _m.sqrt(max(0.0, 1.0 - cos_a * cos_a)))
    inits = [
        np.array([0.0, 0.0, d12, 0.0, tri_pt[0], tri_pt[1], *radii_ideal]),
        np.array([0.0, 0.0, 0.25 * radii_ideal[0], 0.0,
                  0.1 * radii_ideal[0], 0.2 * radii_ideal[1], *radii_ideal]),
        np.array([-1.1 * r_max0, 0.6 * r_max0, 1.1 * r_max0, 0.6 * r_max0,
                  0.0, -0.8 * r_max0, *radii_ideal]),
    ]
    lo = np.array([-np.inf] * 6 + [0.02 * r for r in radii_ideal])
    best = None
    for x0 in inits:
        sol = least_squares(residuals, x0, bounds=(lo, np.inf), diff_step=1e-3,
                            xtol=1e-14, ftol=1e-14, max_nfev=1200)
        sol = least_squares(residuals, sol.x, bounds=(lo, np.inf), diff_step=1e-4,
                            xtol=1e-15, ftol=1e-15, max_nfev=1200)
        if best is None or sol.cost < best.cost:
            best = sol
    sol = best
    centers = [(sol.x[0], sol.x[1]), (sol.x[2], sol.x[3]), (sol.x[4], sol.x[5])]
    radii = [float(sol.x[6]), float(sol.x[7]), float(sol.x[8])]
    # 精细网格硬面积复算（报告 + 质心），与目标函数解耦
    all_r = max(radii)
    xs = [c[0] for c in centers]
    ys = [c[1] for c in centers]
    box = (min(xs) - all_r - 1.0, min(ys) - all_r - 1.0,
           max(xs) + all_r + 1.0, max(ys) + all_r + 1.0)
    areas, cents, _cell = _venn_region_masks(centers, radii, box, 500)
    nz = [abs(areas[k] - target[k]) / target[k] for k in target if target[k] > 0]
    max_rel = max(nz) if nz else 0.0
    centers_u, radii_u, (cx, cy, s) = _fit_into_unit(centers, radii)
    cents_u = {k: (None if v is None else ((v[0] - cx) * s + 0.5, (v[1] - cy) * s + 0.5))
               for k, v in cents.items()}
    fit = {"max_rel_err": max_rel, "centroids": cents_u}
    return centers_u, radii_u, fit


# ── v2.8 D1：venn 4 集合（椭圆风车布局）──────────────────────────────────
_V4_R, _V4_A, _V4_B = 0.10, 0.32, 0.20  # 布局常数：网格探针验证 15 区域全非空


def _venn4_ells(r=_V4_R, a=_V4_A, b=_V4_B):
    """默认 4 椭圆布局（径向风车式，坐标中心为原点）：[(cx,cy,a,b,θrad)×4]。"""
    import math as _m
    return [(r * _m.cos(_m.pi / 2 + i * _m.pi / 2),
             r * _m.sin(_m.pi / 2 + i * _m.pi / 2), a, b,
             _m.pi / 2 + i * _m.pi / 2) for i in range(4)]


def _venn4_region_masks(ells, box, res):
    """网格化 4 椭圆的 15 个区域（确定性，无随机）。ells=[(cx,cy,a,b,θ)]，
    返回 (areas, centroids, cell_area)，键为成员并排序号 "1".."4"/"12"/"1234"；
    空区域 centroids=None。"""
    import itertools as _it
    xs = np.linspace(box[0], box[2], res)
    ys = np.linspace(box[1], box[3], res)
    X, Y = np.meshgrid(xs, ys)
    cell = (box[2] - box[0]) * (box[3] - box[1]) / (res * res)
    ins = []
    for (cx, cy, a, b, th) in ells:
        ct, st = np.cos(th), np.sin(th)
        dx, dy = X - cx, Y - cy
        u = dx * ct + dy * st
        v = -dx * st + dy * ct
        ins.append((u * u) / (a * a) + (v * v) / (b * b) <= 1.0)
    areas, cents = {}, {}
    for n in (1, 2, 3, 4):
        for combo in _it.combinations(range(4), n):
            m = np.ones_like(X, dtype=bool)
            for i in range(4):
                m = m & (ins[i] if i in combo else ~ins[i])
            key = "".join(str(i + 1) for i in combo)
            cnt = int(m.sum())
            areas[key] = cnt * cell
            cents[key] = (float(X[m].mean()), float(Y[m].mean())) if cnt else None
    return areas, cents, cell


def _venn4_geometry(regions, keys):
    """4 集合 --area：椭圆联合最优拟合（eulerAPE 思路，零新依赖）。

    (cx,cy,a,b,θ)×4 最小二乘，残差=15 区域网格面积 vs 目标比例；低分辨率网格
    定向 + 高分辨率复核（全程确定性）。任意 15 区域面积组合在椭圆几何下可能
    无解——非零区域最大面积相对偏差如实写入 fit["max_rel_err"] 由调用方披露。
    返回 (ells_unit, fit)；ells_unit 已归一到 [0,1]²，fit["centroids"] 同坐标系。"""
    import itertools as _it
    import math as _m
    from scipy.optimize import least_squares
    idx = {}
    for n in (1, 2, 3, 4):
        for combo in _it.combinations(range(4), n):
            idx["".join(keys[i] for i in combo)] = "".join(str(i + 1) for i in combo)
    target = {mk: float(regions[nk]) for nk, mk in idx.items()}
    tsum = sum(target.values()) or 1.0

    def residuals(p, res):
        ells = [(p[5 * i], p[5 * i + 1], abs(p[5 * i + 2]), abs(p[5 * i + 3]),
                 p[5 * i + 4]) for i in range(4)]
        got, _ce, _cl = _venn4_region_masks(ells, (-0.6, -0.6, 0.6, 0.6), res)
        gsum = sum(got.values()) or 1.0
        s = tsum / gsum
        out = []
        for mk in sorted(target):
            t = target[mk]
            if t > 0:
                out.append((got[mk] * s - t) / max(t, 1.0))
            else:
                out.append(0.3 * min(got[mk] * s, 1.0))  # 零目标区域温和压空
        return out

    lo, hi = [], []
    for _ in range(4):
        lo += [-0.6, -0.6, 0.05, 0.04, -2 * _m.pi]
        hi += [0.6, 0.6, 0.85, 0.85, 2 * _m.pi]
    lo, hi = np.array(lo), np.array(hi)
    x0 = []
    for (cx, cy, a, b, th) in _venn4_ells():
        x0 += [cx, cy, a, b, th]
    x0 = np.array(x0)
    scale0 = np.array([1, 1, 0.8, 0.8, 1] * 4)
    best = None
    for s0 in (x0, x0 * scale0, np.clip(x0 * 1.1, lo, hi)):
        sol = least_squares(residuals, np.clip(s0, lo, hi), bounds=(lo, hi),
                            args=(200,), diff_step=1e-2, xtol=1e-10, ftol=1e-10,
                            max_nfev=400)
        sol = least_squares(residuals, sol.x, bounds=(lo, hi), args=(320,),
                            diff_step=3e-3, xtol=1e-12, ftol=1e-12, max_nfev=500)
        if best is None or sol.cost < best.cost:
            best = sol
    p = best.x
    ells = [(p[5 * i], p[5 * i + 1], abs(p[5 * i + 2]), abs(p[5 * i + 3]),
             p[5 * i + 4]) for i in range(4)]
    E = max(max(abs(e[0]) + e[2], abs(e[1]) + e[2]) for e in ells) or 1.0
    s = 0.42 / E
    ells_u = [(e[0] * s + 0.5, e[1] * s + 0.5, e[2] * s, e[3] * s, e[4])
              for e in ells]
    areas, cents, _c = _venn4_region_masks(ells_u, (0.0, 0.0, 1.0, 1.0), 620)
    gsum = sum(areas.values()) or 1.0
    s2 = tsum / gsum
    nz = [abs(areas[mk] * s2 - t) / t for mk, t in target.items() if t > 0]
    fit = {"max_rel_err": (max(nz) if nz else 0.0), "centroids": cents}
    return ells_u, fit


def _declutter_points(points, min_dist=0.078, iters=48, relax=0.6):
    """确定性标签疏散：对过近标签对做对称排斥迭代（无随机，同输入同结果）。
    points: {key: (x, y)}；返回新 dict（仅移动过近者，其余原位）。"""
    pts = {k: [float(v[0]), float(v[1])] for k, v in sorted(points.items())
           if v is not None}
    keys = sorted(pts)
    for _ in range(iters):
        moved = False
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b = pts[keys[i]], pts[keys[j]]
                dx, dy = b[0] - a[0], b[1] - a[1]
                dist = (dx * dx + dy * dy) ** 0.5
                if dist >= min_dist:
                    continue
                if dist < 1e-9:
                    dx, dy, dist = 1.0, 0.0, 1.0
                push = (min_dist - dist) * relax / 2.0
                ux, uy = dx / dist, dy / dist
                pts[keys[i]][0] -= ux * push
                pts[keys[i]][1] -= uy * push
                pts[keys[j]][0] += ux * push
                pts[keys[j]][1] += uy * push
                moved = True
        if not moved:
            break
    return {k: tuple(v) for k, v in pts.items()}


def _gen_venn4(ax, keys, regions, colors, fs, cjk_fp, area_mode):
    """v2.8 D1：4 集合韦恩绘制（椭圆）。默认=固定风车布局、15 区域计数全标；
    area_mode=按面积比例最优拟合（残差中文披露，数字仍为精确计数）。"""
    import itertools as _it
    import math as _m
    import matplotlib.patches as mpatches
    if area_mode:
        ells, fit = _venn4_geometry(regions, keys)
        _ar, cents, _c = _venn4_region_masks(ells, (0.0, 0.0, 1.0, 1.0), 620)
        max_rel = fit["max_rel_err"]
        if max_rel <= 0.05:
            print(f"venn --area: 4 集合椭圆拟合完成"
                  f"（最大区域面积偏差 {max_rel * 100:.1f}%）", file=sys.stderr)
        else:
            _warn(f"venn --area: 15 个区域面积在椭圆几何下无法完全按比例实现，"
                  f"已取最优拟合（最大面积偏差 {max_rel * 100:.1f}%）；"
                  f"区域数字仍为精确计数")
            if max_rel > 0.15:
                _warn("venn --area: 偏差较大——可尝试 ①减少集合数（2~3 集合拟合更准）"
                      "②去掉占比悬殊的区域 ③改用默认等圆模式（放弃面积比例）")
    else:
        ells = [(cx + 0.5, cy + 0.5, a, b, th)
                for (cx, cy, a, b, th) in _venn4_ells()]
        _ar, cents, _c = _venn4_region_masks(ells, (0.0, 0.0, 1.0, 1.0), 420)

    for i in range(4):
        cx, cy, a, b, th = ells[i]
        ax.add_patch(mpatches.Ellipse(
            (cx, cy), 2 * a, 2 * b, angle=_m.degrees(th),
            facecolor=colors[i % len(colors)], edgecolor="#333333",
            linewidth=1.4, alpha=0.42, zorder=2))

    zero_regions = []
    label_plan = []  # (mkey, cnt, pos)：先收集，疏散后统一画（中心 5 区域质心彼此很近）
    for n in (1, 2, 3, 4):
        for combo in _it.combinations(range(4), n):
            mkey = "".join(str(i + 1) for i in combo)
            rname = "".join(keys[i] for i in combo)
            cnt = regions[rname]
            pos = cents.get(mkey)
            if pos is None:
                if cnt > 0:
                    _warn(f"venn: 区域 '{rname}' 面积过小，计数标注在近似位置")
                    members = [i for i in range(4) if str(i + 1) in mkey]
                    pos = (sum(ells[i][0] for i in members) / len(members),
                           sum(ells[i][1] for i in members) / len(members))
                else:
                    zero_regions.append(rname)
                    continue
            if area_mode and cnt <= 0:
                zero_regions.append(rname)
                continue
            label_plan.append((mkey, cnt, pos))
    spread = _declutter_points({mk: p for mk, _c, p in label_plan})
    for mk, cnt, _p in label_plan:
        ax.annotate(str(cnt), spread[mk], fontsize=fs, ha="center", va="center",
                    fontweight="bold", color="#333333", zorder=6)
    if zero_regions and area_mode:
        _warn(f"venn --area: 区域 {zero_regions} 计数为 0，无对应面积，图中省略数字")

    for i, k in enumerate(keys):
        cx, cy, a_i, _b, _th = ells[i]
        dx, dy = cx - 0.5, cy - 0.5
        norm = _m.hypot(dx, dy)
        if norm < 1e-9:
            dx, dy, norm = 0.0, 1.0, 1.0
        dist = norm + a_i + 0.035  # 椭圆尖端外侧——计数在区域质心，两者不相撞
        lx = 0.5 + dx / norm * dist
        ly = 0.5 + dy / norm * dist
        lx = min(1.06, max(-0.06, lx))
        ly = min(1.06, max(-0.06, ly))
        ax.annotate(k, (lx, ly), fontsize=fs, fontweight="bold",
                    ha="center", va="center",
                    fontproperties=_fp(cjk_fp, k), color="#333333", zorder=5)


def gen_venn(data, ax, theme, cjk_fp, **kwargs):
    """韦恩图（2~4 集合；4 集合为椭圆布局，v2.8）。默认等圆/等椭圆示意、区域数字精确；--area 开面积比例
    （Euler）模式：圆的大小与交集面积按区域计数比例（2 集合解析解，
    3 集合圆心+半径联合最优拟合）。

    数据两种格式（二选一）:
      {"sets": {"A": [元素...], "B": [...]}} —— 元素列表，自动求交并（2~3 集合）
      {"regions": {"A": 30, "B": 25, "AB": 9}} —— 全部区域计数：
        2 集合恰 3 键 {A, B, A+B}；3 集合恰 7 键 {A,B,C,A+B,A+C,B+C,A+B+C}。
        （v2.3 的数字型 sets 因键数歧义从未可用，v2.5 起以独立键 'regions' 修复）
    """
    import matplotlib.patches as mpatches
    sets = data.get("sets", None)
    regs = data.get("regions", None)
    keys = None
    if isinstance(sets, dict) and 2 <= len(sets) <= 4 and all(
            isinstance(v, (list, tuple, set)) for v in sets.values()):
        if regs is not None:
            raise ValueError("venn: 'sets' 与 'regions' 只能二选一")
        keys = [str(k) for k in sets.keys()]
        ss = {k: set(sets[k]) for k in keys}
        regions = {}
        if len(keys) == 2:
            A, B = ss[keys[0]], ss[keys[1]]
            regions = {keys[0]: len(A - B), keys[1]: len(B - A),
                       keys[0] + keys[1]: len(A & B)}
        elif len(keys) == 3:
            A, B, C = ss[keys[0]], ss[keys[1]], ss[keys[2]]
            regions = {keys[0]: len(A - B - C), keys[1]: len(B - A - C),
                       keys[2]: len(C - A - B),
                       keys[0] + keys[1]: len((A & B) - C),
                       keys[0] + keys[2]: len((A & C) - B),
                       keys[1] + keys[2]: len((B & C) - A),
                       keys[0] + keys[1] + keys[2]: len(A & B & C)}
        else:  # v2.8：4 集合 → 15 区域
            import itertools as _it4
            for _n in (1, 2, 3, 4):
                for _combo in _it4.combinations(range(4), _n):
                    _inter = set(ss[keys[_combo[0]]])
                    for _i in _combo[1:]:
                        _inter &= ss[keys[_i]]
                    for _i in range(4):
                        if _i not in _combo:
                            _inter -= ss[keys[_i]]
                    regions["".join(keys[_i] for _i in _combo)] = len(_inter)
    elif isinstance(sets, dict):
        raise ValueError("venn: 'sets' 需为 2~4 个集合、值为元素列表的字典；"
                         "区域计数请改用 'regions' 键")
    elif isinstance(regs, dict):
        all_keys = [str(k) for k in regs.keys()]
        for k in all_keys:
            v = regs[k]
            if not isinstance(v, (int, float)) or v < 0:
                raise ValueError(f"venn: 区域 '{k}' 需为非负数字（元素个数）")
        found = None
        if len(all_keys) == 3:
            for a in all_keys:
                for b in all_keys:
                    if a == b:
                        continue
                    if {a, b, a + b} == set(all_keys):
                        found = [a, b]  # 集合名只有两个，第三个键是交集计数
                        break
                if found:
                    break
        elif len(all_keys) == 7:
            for a in all_keys:
                for b in all_keys:
                    for c in all_keys:
                        if a == b or b == c or a == c:
                            continue
                        need = {a, b, c, a + b, a + c, b + c, a + b + c}
                        if need == set(all_keys):
                            found = [a, b, c]
        elif len(all_keys) == 15:  # v2.8：4 集合 15 区域
            import itertools as _it4
            for _names in _it4.permutations(all_keys, 4):
                _need = set()
                for _n in (1, 2, 3, 4):
                    for _combo in _it4.combinations(_names, _n):
                        _need.add("".join(_combo))
                if _need == set(all_keys):
                    found = list(_names)
                    break
        if not found:
            raise ValueError("venn: 'regions' 键名不构成合法区域集——2 集合需恰 "
                             "{A, B, A+B} 三键；3 集合需恰 {A,B,C,A+B,A+C,B+C,"
                             "A+B+C} 七键；4 集合需恰 15 键（A,B,C,D,A+B,…,A+B+C+D；"
                             "当前: " + ",".join(all_keys) + "）")
        keys = found
        regions = {r: int(regs[r]) for r in all_keys}
    else:
        raise ValueError("venn: 需要 'sets'（元素列表字典）或 'regions'（区域计数）")

    def _fallback_pos(region, keys, centers):
        parts = [keys.index(k) for k in keys if k in region] or [0]
        n = len(parts)
        return (sum(centers[i][0] for i in parts) / n,
                sum(centers[i][1] for i in parts) / n)

    colors = theme["colors"][:len(keys)]
    fs = theme["font_size"] + 2
    area_mode = bool(kwargs.get("area_mode"))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_aspect("equal"); ax.axis("off")
    if len(keys) == 4:  # v2.8 D1：4 集合走椭圆布局（默认与 --area 皆支持）
        _gen_venn4(ax, keys, regions, colors, fs, cjk_fp, area_mode)
        return

    if area_mode:
        # ── Euler 面积比例模式：圆的大小与交集面积按计数比例 ──
        import math as _m
        if len(keys) == 2:
            k1, k2 = keys
            centers, radii, vnotes = _venn2_geometry(regions[k1], regions[k2],
                                                     regions[k1 + k2])
            all_r = max(radii)
            xs = [c[0] for c in centers]
            ys = [c[1] for c in centers]
            box = (min(xs) - all_r - 0.05, min(ys) - all_r - 0.05,
                   max(xs) + all_r + 0.05, max(ys) + all_r + 0.05)
            areas, cents, _cell = _venn_region_masks(centers, radii, box, 900)
            cent_by_key = {k1: cents["1"], k2: cents["2"], k1 + k2: cents["12"]}
            fit_err = None
        else:
            k1, k2, k3 = keys
            centers, radii, fit = _venn3_geometry(regions, keys)
            idx = {k1: "1", k2: "2", k3: "3", k1 + k2: "12", k1 + k3: "13",
                   k2 + k3: "23", k1 + k2 + k3: "123"}
            cent_by_key = {rk: fit["centroids"][mk] for rk, mk in idx.items()}
            fit_err = fit["max_rel_err"]
            vnotes = []
        for msg in vnotes:
            _warn(f"venn --area: {msg}")
        if fit_err is not None:
            if fit_err <= 0.05:
                print(f"venn --area: 面积比例拟合完成（最大区域面积偏差 {fit_err*100:.1f}%）",
                      file=sys.stderr)
            else:
                _warn(f"venn --area: 区域计数在几何上难以完全按比例呈现，已取最优拟合"
                      f"（最大面积偏差 {fit_err*100:.1f}%）；区域数字仍为精确计数")
        for i, k in enumerate(keys):
            cx, cy = centers[i]
            r_draw = max(radii[i], 0.012)
            ax.add_patch(mpatches.Circle((cx, cy), r_draw, facecolor=colors[i],
                                         edgecolor="#333333", linewidth=1.4,
                                         alpha=0.42, zorder=2))
        # 集合名：沿 圆心→图心 反向推到圆外（角度逐个微错开防同心/子集情形相撞）
        for i, k in enumerate(keys):
            cx, cy = centers[i]
            r_draw = max(radii[i], 0.012)
            dx, dy = cx - 0.5, cy - 0.5
            norm = _m.hypot(dx, dy) or 1.0
            ang = _m.atan2(dy / norm, dx / norm) + i * 0.25
            lx = cx + _m.cos(ang) * (r_draw + 0.10)
            ly = cy + _m.sin(ang) * (r_draw + 0.10)
            ax.annotate(k, (lx, ly), fontsize=fs, fontweight="bold",
                        ha="center", va="center",
                        fontproperties=_fp(cjk_fp, k), color="#333333", zorder=5)
        # 区域计数：放网格质心（视觉中心即数学中心）
        zero_regions = [r for r, v in regions.items() if v <= 0]
        for region, cnt in regions.items():
            if cnt <= 0:
                continue
            pos = cent_by_key.get(region)
            if pos is None:
                pos = _fallback_pos(region, keys, centers)
                _warn(f"venn --area: 区域 '{region}' 面积过小，计数标注在近似位置")
            ax.annotate(str(cnt), pos, fontsize=fs, ha="center", va="center",
                        fontweight="bold", color="#333333", zorder=6)
        if zero_regions:
            _warn(f"venn --area: 区域 {zero_regions} 计数为 0，无对应面积，图中省略数字")
    else:
        # ── 等圆示意模式（默认）：区域数字精确，面积不按比例 ──
        if len(keys) == 2:
            centers = [(0.62, 0.5), (0.38, 0.5)]
            r = 0.27
            # 区域标签绝对坐标（与圆心几何对应）
            k1, k2 = keys
            label_xy = {k1: (0.76, 0.5), k2: (0.24, 0.5), k1 + k2: (0.5, 0.5)}
        else:
            centers = [(0.60, 0.62), (0.40, 0.62), (0.50, 0.40)]
            r = 0.235
            k1, k2, k3 = keys
            label_xy = {k1: (0.745, 0.64), k2: (0.255, 0.64), k3: (0.50, 0.245),
                        k1 + k2: (0.50, 0.705), k1 + k3: (0.585, 0.462),
                        k2 + k3: (0.415, 0.462), k1 + k2 + k3: (0.50, 0.535)}
        # 标签偏移与圈位同侧：圈1 在右(0.60)、圈2 在左(0.40)、圈3 在下——
        # 旧版偏移镜像导致前两个集合的名称互相标到对方的圈上（标签-圈错位 bug）
        label_pos = [(0.24, 0.16), (-0.24, 0.16), (0.0, -0.26)] if len(keys) == 3 \
            else [(0.24, 0.0), (-0.24, 0.0)]
        for i, k in enumerate(keys):
            cx, cy = centers[i]
            ax.add_patch(mpatches.Circle((cx, cy), r, facecolor=colors[i],
                                         edgecolor="#333333", linewidth=1.4,
                                         alpha=0.42, zorder=2))
            lx, ly = label_pos[i]
            ax.annotate(k, (cx + lx * 1.15, cy + ly * 1.15), fontsize=fs,
                        fontweight="bold", ha="center", va="center",
                        fontproperties=_fp(cjk_fp, k), color="#333333", zorder=5)
        for region, cnt in regions.items():
            lx, ly = label_xy[region]
            ax.annotate(str(cnt), (lx, ly), fontsize=fs,
                        ha="center", va="center", fontweight="bold", color="#333333",
                        zorder=6)
    total = sum(regions.values())
    ax.set_title(f"n = {total}") if not data.get("title") else None
    return None


# ── cluster_heatmap 聚类热图 ──────────────────────────────────────────

def gen_cluster_heatmap(data, ax, theme, cjk_fp, **kwargs):
    """聚类热图：行列按层次聚类（Ward）重排后绘制（v2.3 不含树状图面板，
    聚类顺序写入 stderr 与 alt 文本；树状图面板计划 v2.4）。

    数据格式同 heatmap：{"matrix": [[...]], "row_labels": [...], "col_labels": [...]}。
    """
    from scipy.cluster.hierarchy import linkage, leaves_list
    matrix = data.get("matrix", data.get("data", data.get("values", None)))
    if matrix is None or not isinstance(matrix, (list, tuple)) or len(matrix) == 0:
        raise ValueError("cluster_heatmap: 需要 'matrix'（二维数值数组）")
    M = np.asarray(matrix, dtype=float)
    if M.ndim != 2 or M.shape[0] < 2 or M.shape[1] < 2:
        raise ValueError(f"cluster_heatmap: 矩阵需 >=2×2（当前 {M.shape}）")
    if M.shape[0] > MAX_CLUSTER_ROWS:
        raise ValueError(f"cluster_heatmap: 行数 {M.shape[0]} 超过聚类上限 {MAX_CLUSTER_ROWS}"
                         f"（层次聚类内存随行数平方增长，请先筛选特征/样本；"
                         f"或加 --downsample 2000 等距采样到 2000 行后重试）")
    if np.any(~np.isfinite(M)):
        raise ValueError("cluster_heatmap: 矩阵含 NaN/Inf——请先补全（聚类不支持缺失值）")
    row_labels = list(data.get("row_labels", data.get("rows", data.get("y_labels", []))))
    col_labels = list(data.get("col_labels", data.get("cols", data.get("x_labels", []))))

    method = kwargs.get("cluster_method", "ward")
    metric = kwargs.get("cluster_metric", "euclidean")
    row_order = np.array(leaves_list(linkage(M, method=method, metric=metric)))
    col_order = np.array(leaves_list(linkage(M.T, method=method, metric=metric)))
    M2 = M[np.ix_(row_order, col_order)]
    rl2 = [row_labels[i] if i < len(row_labels) else f"行{i+1}" for i in row_order]
    cl2 = [col_labels[i] if i < len(col_labels) else f"列{i+1}" for i in col_order]

    ax._af_category_axis = True  # 行列标签是数据：豁免 fix_tick_overlaps 降级
    cmap = kwargs.get("cmap") or "RdBu_r"
    vmin = kwargs.get("vmin", None) or float(M2.min())
    vmax = kwargs.get("vmax", None) or float(M2.max())
    if vmin == vmax:
        vmin, vmax = vmin - 1e-9, vmax + 1e-9
    im = ax.imshow(M2, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax,
                   interpolation="nearest")
    ax.set_xticks(range(len(cl2)))
    ax.set_xticklabels(cl2, rotation=45, ha="right",
                       fontsize=max(6, theme["font_size"] - 2),
                       fontproperties=_fp(cjk_fp, " ".join(map(str, cl2))))
    ax.set_yticks(range(len(rl2)))
    ax.set_yticklabels(rl2, fontsize=max(6, theme["font_size"] - 2),
                       fontproperties=_fp(cjk_fp, " ".join(map(str, rl2))))
    for spine in ax.spines.values():
        spine.set_visible(False)
    if kwargs.get("show_values"):
        for i in range(M2.shape[0]):
            for j in range(M2.shape[1]):
                ax.text(j, i, f"{M2[i, j]:.1f}", ha="center", va="center",
                        fontsize=max(5, theme["font_size"] - 3),
                        color="white" if abs(M2[i, j] - (vmin+vmax)/2) > (vmax-vmin)/4 else "#333333")
    _warn(f"cluster_heatmap: 行聚类顺序 {rl2[:8]}{'…' if len(rl2) > 8 else ''}；"
          f"列聚类顺序 {cl2[:8]}{'…' if len(cl2) > 8 else ''}（method={method}/{metric}）")
    return im  # 交给主流程挂色条


# ── 注册表 ────────────────────────────────────────────────────────────

EXTRA_GENERATORS = {
    "funnel": gen_funnel,
    "bland_altman": gen_bland_altman,
    "pca": gen_pca,
    "paired": gen_paired,
    "venn": gen_venn,
    "cluster_heatmap": gen_cluster_heatmap,
}

EXTRA_DEMO_DATA = {
    "funnel": {"studies": [
        {"name": "Smith 2020", "effect": 0.69, "se": 0.12},
        {"name": "Lee 2021", "effect": 0.55, "se": 0.20},
        {"name": "王 2022", "effect": 0.80, "se": 0.09},
        {"name": "Garcia 2023", "effect": 0.42, "se": 0.31},
        {"name": "陈 2024", "effect": 0.61, "se": 0.15},
        {"name": "Kim 2025", "effect": 0.73, "se": 0.11},
    ]},
    "bland_altman": {"methods": {"新仪器": [5.1, 4.9, 5.3, 5.6, 4.8, 5.2, 5.0, 5.5],
                                 "金标准": [5.0, 5.1, 5.2, 5.4, 5.0, 5.1, 5.2, 5.3]}},
    "pca": {"matrix": [[5.1, 3.5, 1.4, 0.2], [4.9, 3.0, 1.4, 0.2], [6.7, 3.1, 4.4, 1.4],
                        [6.0, 2.9, 4.5, 1.5], [6.3, 3.3, 6.0, 2.5], [5.8, 2.7, 5.1, 1.9],
                        [4.7, 3.2, 1.3, 0.2], [6.1, 2.8, 4.7, 1.2]],
            "groups": ["setosa", "setosa", "versicolor", "versicolor",
                       "virginica", "virginica", "setosa", "versicolor"],
            "feature_names": ["萼长", "萼宽", "瓣长", "瓣宽"]},
    "paired": {"series": {"术前": [8.2, 7.5, 9.1, 6.8, 7.9, 8.5],
                           "术后": [6.1, 5.8, 7.2, 5.0, 6.3, 6.9]}},
    "venn": {"sets": {"基因集A": ["TP53", "BRCA1", "EGFR", "MYC", "KRAS", "PTEN"],
                      "基因集B": ["TP53", "EGFR", "ALK", "ROS1"],
                      "基因集C": ["TP53", "MYC", "ALK", "NRAS"]}},
    "cluster_heatmap": {"matrix": [[2.1, 0.3, 1.8, 0.1], [1.9, 0.2, 2.0, 0.3],
                                    [0.2, 2.2, 0.1, 1.9], [0.3, 2.0, 0.4, 2.1],
                                    [1.8, 0.4, 1.9, 0.2], [0.1, 1.8, 0.3, 2.0]],
                         "row_labels": ["样本1", "样本2", "样本3", "样本4", "样本5", "样本6"],
                         "col_labels": ["基因A", "基因B", "基因C", "基因D"]},
}


# ── validate / alt / caption 钩子 ─────────────────────────────────────

def validate_extra(chart_type, data):
    """新图型数据校验。返回 (fatal, warn) 两条列表（信息可含修正指引）。"""
    fatal, warns = [], []
    if chart_type == "funnel":
        studies = data.get("studies", None)
        if not studies and (data.get("effects") is None or data.get("ses") is None):
            fatal.append("funnel: 需要 'studies'（每项含 name/effect/se）或 'effects'+'ses'")
        elif studies:
            bad = [i for i, s in enumerate(studies)
                   if not isinstance(s, dict) or "effect" not in s or "se" not in s]
            if bad:
                fatal.append(f"funnel: studies 第 {bad[:3]} 项缺少 effect 或 se 字段")
    elif chart_type == "bland_altman":
        if ("a" not in data or "b" not in data) and not isinstance(data.get("methods"), dict):
            fatal.append("bland_altman: 需要 'a'+'b' 数组或 'methods' 两个系列")
    elif chart_type == "pca":
        m = data.get("matrix")
        if not m:
            fatal.append("pca: 需要 'matrix'（行=样本 列=特征）")
        elif len(m[0]) > MAX_PCA_COLS:
            fatal.append(f"pca: 特征列 {len(m[0])} 超上限 {MAX_PCA_COLS}")
    elif chart_type == "paired":
        if ("before" not in data or "after" not in data) and not isinstance(data.get("series"), dict):
            fatal.append("paired: 需要 'before'+'after' 或 'series' 恰好两项")
    elif chart_type == "venn":
        s = data.get("sets")
        rg = data.get("regions")
        ok_sets = (isinstance(s, dict) and 2 <= len(s) <= 4 and not rg  # v2.8：4 集合
                   and all(isinstance(v, (list, tuple, set)) for v in s.values()))
        ok_regs = isinstance(rg, dict) and len(rg) in (3, 7, 15) and not s  # v2.8：15 键
        if not (ok_sets or ok_regs):
            fatal.append("venn: 需要 'sets'（2~4 个集合，值为元素列表）或 'regions'"
                         "（区域计数：2 集合恰 {A,B,A+B} 三键 / 3 集合恰 7 键 /"
                         " 4 集合恰 15 键）")
    elif chart_type == "cluster_heatmap":
        m = data.get("matrix", data.get("data", data.get("values")))
        if m is None:
            fatal.append("cluster_heatmap: 需要 'matrix'")
        elif isinstance(m, (list, tuple)) and len(m) > MAX_CLUSTER_ROWS:
            fatal.append(f"cluster_heatmap: 行数 {len(m)} 超过聚类上限 {MAX_CLUSTER_ROWS}"
                         "（可加 --downsample 2000 等距采样后重试）")
    return fatal, warns


def alt_extra(chart_type, data, title=""):
    """新图型的无障碍描述（--alt）。"""
    t = f"{title}。" if title else ""
    if chart_type == "funnel":
        n = len(data.get("studies", data.get("effects", [])) or [])
        return f"{t}漏斗图，含 {n} 个研究的效应值散点、DerSimonian-Laird 合并效应线与 95% 伪置信漏斗线。"
    if chart_type == "bland_altman":
        a = data.get("a") or (data.get("methods") or {}).get(list(data.get("methods", {}))[0], [])
        return f"{t}Bland-Altman 一致性图，{len(a)} 对测量的差值-均值散点，含均值差线与 95% 一致性界线。"
    if chart_type == "pca":
        m = data.get("matrix") or []
        return f"{t}PCA 得分图，{len(m)} 个样本投影到前两个主成分平面，橙色箭头为主要载荷特征。"
    if chart_type == "paired":
        b = data.get("before") or []
        return f"{t}配对前后图，{len(b)} 个受试对象各一条灰色折线连接前后两次测量，附配对检验显著性。"
    if chart_type == "venn":
        s = data.get("sets") or {}
        return f"{t}韦恩图，{len(s)} 个集合的交并关系，各区域标注元素个数（不按面积比例）。"
    if chart_type == "cluster_heatmap":
        m = data.get("matrix") or []
        return f"{t}聚类热图，{len(m)} 行按层次聚类重排，颜色深浅映射数值高低。"
    return t or f"{chart_type} 图。"


# ── 图注模板（--caption，中英双语并列） ────────────────────────────────

def make_caption(chart_type, data, title=""):
    """期刊式图注（中英双语并列），写 <out>.caption.txt。渲染失败不阻断出图。"""
    zh_head = f"{title}。" if title else ""
    en_head = ""
    def _n(key, default="?"):
        v = data.get(key)
        return str(len(v)) if isinstance(v, (list, dict, tuple)) else default
    T = {
        "bar": ("柱状图展示各组测量值（n 组）。",
                "Bar chart of measurements across groups."),
        "box": (f"箱线图展示 {_n('series')} 组分布：箱体=四分位距，横线=中位数，须线=1.5×IQR。",
                f"Box plots of {len(data.get('series', {}) or [])} groups: box = IQR, line = median, whiskers = 1.5×IQR."),
        "violin": (f"小提琴图展示 {_n('series')} 组分布（核密度估计），内部箱线为中位数与四分位。",
                "Violin plots (kernel density) with inner box (median and IQR)."),
        "km": ("Kaplan-Meier 生存曲线（纵轴生存概率，横轴时间），下方风险表为各时间点仍处于风险的人数；log-rank 检验。",
               "Kaplan-Meier survival curves with numbers at risk; log-rank test."),
        "roc": ("ROC 曲线，AUC 量化判别能力（0.5=无判别，1.0=完美）。",
                "ROC curves; AUC quantifies discrimination."),
        "forest": ("森林图：各方块为各研究效应值（面积∝权重），横线为 95%CI，菱形为合并效应。",
                   "Forest plot: squares = study effects (area ∝ weight), lines = 95% CI, diamond = pooled effect."),
        "heatmap": ("热图，颜色深浅映射数值大小（见色条）。",
                    "Heatmap; color intensity maps value (see colorbar)."),
        "scatter": ("散点图及线性趋势线。",
                    "Scatter plot with linear trend."),
        "line": ("折线图展示随 x 变化的趋势。",
                 "Line plot of trends."),
        "funnel": ("漏斗图：各研究效应值 vs 标准误，虚线为 95% 伪置信界，竖线为 DL 随机效应合并值。",
                   "Funnel plot: study effects vs SE, dashed pseudo-95% CI bounds, vertical line = DL pooled estimate."),
        "bland_altman": ("Bland-Altman 图：横轴两法均值、纵轴差值；实线=均值差，虚线=95% 一致性界值。",
                         "Bland-Altman plot: mean vs difference; solid = mean difference, dashed = 95% limits of agreement."),
        "pca": ("PCA 得分图（PC1×PC2，标准化后），椭圆为各组均值±2SD，箭头为载荷前 5 特征。",
                "PCA score plot (PC1×PC2, standardized); ellipses = group mean±2SD; arrows = top-5 loadings."),
        "paired": ("配对前后图：每受试对象一条折线连接前后测量，星号为配对检验显著性。",
                   "Paired before-after plot: one line per subject; stars denote paired-test significance."),
        "venn": ("韦恩图展示集合交并（区域数字=元素个数，非面积比例）。",
                 "Venn diagram of set intersections (region labels = counts, not area-proportional)."),
        "cluster_heatmap": ("聚类热图：行/列按 Ward 层次聚类重排，颜色映射数值（见色条）。",
                            "Clustered heatmap: rows/columns reordered by Ward linkage; color maps values."),
    }
    zh, en = T.get(chart_type, (f"{chart_type} 图。", f"{chart_type} figure."))
    if title:
        zh_full = f"图：{zh_head}{zh}"
        en_full = f"Fig. {title}. {en}"
    else:
        zh_full = zh
        en_full = en
    return f"{zh_full}\n{en_full}"
