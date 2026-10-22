





import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional, Tuple






def sanitize_value(v, ndigits: Optional[int] = 2):




    if isinstance(v, float):
        if np.isnan(v) or np.isinf(v):
            return None
        return round(v, ndigits) if ndigits is not None else v
    return v


def sanitize_series(data, ndigits: Optional[int] = 2) -> List[Any]:
    return [sanitize_value(v, ndigits) for v in data]


def pt(v) -> Optional[float]:

    if v is None:
        return None
    try:
        f = float(v)
        if pd.isna(f):
            return None
        return round(f, 2)
    except (TypeError, ValueError):
        return None


def fmt_num(v) -> str:

    s = f'{v:,.2f}'.rstrip('0').rstrip('.')
    return '0' if s in ('', '-', '-0') else s


def safe_str_series(series) -> pd.Series:





    if isinstance(series.dtype, pd.CategoricalDtype):
        series = series.astype('object')
    return series.fillna('').astype(str)


def safe_str_list(series) -> List[str]:
    return safe_str_series(series).tolist()


def name_value_pairs(names, values, ndigits: Optional[int] = 2) -> List[Dict[str, Any]]:

    return [{'name': str(n), 'value': sanitize_value(float(v), ndigits)}
            for n, v in zip(names, values)]






def gauge_scale(data_max: float) -> float:





    if data_max <= 1.0:
        return 1.0
    if data_max <= 100.0:
        return 100.0
    return data_max * 1.05


def sturges_bins(values) -> Tuple[np.ndarray, np.ndarray]:

    n_bins = max(10, int(np.log2(len(values)) + 1))
    return np.histogram(values, bins=n_bins)


def bin_labels(edges, counts) -> List[str]:

    labels = [f'[{edges[i]:.1f}, {edges[i + 1]:.1f})' for i in range(len(counts))]
    labels[-1] = labels[-1][:-1] + ']'
    return labels


def box_stats(s: pd.Series) -> Dict[str, Any]:

    q1, q2, q3 = float(s.quantile(0.25)), float(s.quantile(0.5)), float(s.quantile(0.75))
    iqr = q3 - q1
    lo = max(float(s.min()), q1 - 1.5 * iqr)
    hi = min(float(s.max()), q3 + 1.5 * iqr)
    outliers = s[(s < lo) | (s > hi)]
    return {'min': lo, 'q1': q1, 'median': q2, 'q3': q3, 'max': hi, 'outliers': outliers}


def waterfall_walk(values) -> Tuple[List[float], List[float], List[str], Dict[str, Any]]:







    base, heights, signeds = [], [], []
    cum = 0.0
    first = None
    max_pos = max_neg = None
    max_pos_i = max_neg_i = None
    for i, v in enumerate(values):
        fv = float(v) if pd.notna(v) else 0.0
        if first is None:
            first = fv
        signeds.append(fmt_num(fv))
        if fv >= 0:
            base.append(round(cum, 2))
            heights.append(round(fv, 2))
            if max_pos is None or fv > max_pos:
                max_pos, max_pos_i = fv, i
        else:
            base.append(round(cum + fv, 2))
            heights.append(round(-fv, 2))
            if max_neg is None or fv < max_neg:
                max_neg, max_neg_i = fv, i
        cum += fv
    stats = {'total_delta': round(cum, 2),
             'first': round(first, 2) if first is not None else None,
             'max_pos_i': max_pos_i, 'max_neg_i': max_neg_i,
             'max_positive': max_pos, 'max_negative': max_neg}
    return base, heights, signeds, stats


def pareto_stats(vals) -> Dict[str, Any]:





    clean = [float(v) for v in vals if v is not None]
    total = float(sum(clean)) or 1.0
    cum_pct: List[float] = []
    c = 0.0
    n80 = None
    for i, v in enumerate(vals, start=1):
        c += float(v) if v is not None else 0.0
        cum_pct.append(round(c / total * 100, 2))
        if n80 is None and c / total >= 0.8:
            n80 = i
    top3 = float(sum(clean[:3]))
    return {'total': round(total, 2), 'n_items': len(vals),
            'top3_share': round(top3 / total, 4),
            'items_to_80pct': n80, 'cum_pct': cum_pct}
