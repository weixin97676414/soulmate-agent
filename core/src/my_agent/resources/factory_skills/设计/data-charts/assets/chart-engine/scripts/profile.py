


















import re
import warnings
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd



_MONTH_LABEL_RE = re.compile(r'^(\d{1,2})\s*月$')

_TIME_PARSE_MIN_RATIO = 0.8

_CORR_STRONG = 0.7

_DIVERGE_DROP = -0.25

_MISSING_ALERT = 0.2


def _f(v) -> Optional[float]:

    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        f = float(v)
        return None if np.isnan(f) or np.isinf(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def _i(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _safe(v):

    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (np.integer, np.floating, np.bool_)):
        return v.item()
    if isinstance(v, (int, float, bool, str)):
        return v
    return str(v)


def build_profile(df: pd.DataFrame) -> Dict[str, Any]:






    try:
        df = df.reset_index(drop=True)
    except Exception:
        pass
    n = int(len(df))
    columns = [_profile_column(df, c) for c in df.columns]
    types = _classify_types(df)
    numeric_cols = types.get('numeric', [])
    
    relations = _relations(df, numeric_cols)
    return {
        'rows': n,
        'cols': int(len(df.columns)),
        'columns': columns,
        'grain': _grain(df),
        'relations': relations,
        'signals': _signals(df, types, relations),
        'row_quality': _row_quality(df),
    }




def _profile_column(df: pd.DataFrame, col: Any) -> Dict[str, Any]:








    s = df[col]
    n = int(len(s))
    nn = s.dropna()
    card = int(s.nunique(dropna=True))
    out: Dict[str, Any] = {
        'name': str(col),
        'dtype': str(s.dtype),
        'cardinality': card,
        'missing': int(s.isna().sum()),
        'missing_rate': round(float(s.isna().mean()), 4) if n else 0.0,
        'sample': [_safe(v) for v in nn.head(5).tolist()],
    }
    if pd.api.types.is_numeric_dtype(s):
        out['numeric'] = _numeric_profile(nn)
    elif pd.api.types.is_datetime64_any_dtype(s) or _looks_like_time(nn):
        out['time'] = _time_profile(nn)
    else:
        vc = nn.astype(str).value_counts()
        out['top_values'] = [{'value': k, 'count': _i(v),
                              'share': round(_i(v) / len(nn), 4) if len(nn) else 0.0}
                             for k, v in vc.head(10).items()]
        if len(vc):
            out['top1_share'] = round(_i(vc.iloc[0]) / len(nn), 4) if len(nn) else 0.0
    return out


def _classify_types(df: pd.DataFrame) -> Dict[str, List[str]]:








    numeric: List[str] = []
    time: List[str] = []
    category: List[str] = []
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            numeric.append(str(c))
        elif pd.api.types.is_datetime64_any_dtype(s) or _looks_like_time(s.dropna().astype(str).str.strip()):
            time.append(str(c))
        else:
            category.append(str(c))
    return {'numeric': numeric, 'time': time, 'category': category}


def _looks_like_time(nn: pd.Series) -> bool:

    if nn.empty:
        return False
    if _MONTH_LABEL_RE.match(nn.iloc[0] or '') and \
            nn.str.match(_MONTH_LABEL_RE).mean() >= _TIME_PARSE_MIN_RATIO:
        return True
    parsed = _try_parse_datetime(nn)
    if parsed is None:
        return False
    return bool(parsed.notna().mean() >= _TIME_PARSE_MIN_RATIO)


def _try_parse_datetime(nn: pd.Series) -> Optional[pd.Series]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            return pd.to_datetime(nn, errors='coerce')
    except Exception:
        return None


def _numeric_profile(nn: pd.Series) -> Dict[str, Any]:
    if nn.empty:
        return {'count': 0}
    q1, med, q3 = (nn.quantile(0.25), nn.quantile(0.5), nn.quantile(0.75))
    iqr = float(q3 - q1)
    lo, hi = float(q1) - 1.5 * iqr, float(q3) + 1.5 * iqr
    outliers = nn[(nn < lo) | (nn > hi)] if iqr > 0 else nn.iloc[0:0]
    return {
        'count': int(len(nn)),
        'min': _f(nn.min()), 'max': _f(nn.max()), 'mean': _f(nn.mean()),
        'median': _f(med), 'std': _f(nn.std()),
        'p25': _f(q1), 'p75': _f(q3),
        'sum': _f(nn.sum()),
        'zeros': int((nn == 0).sum()),
        'negatives': int((nn < 0).sum()),
        'outliers': int(len(outliers)),
        'monotonic': bool(nn.is_monotonic_increasing or nn.is_monotonic_decreasing),
    }


def _time_profile(nn: pd.Series) -> Dict[str, Any]:
    vals = _order_values(nn)
    out: Dict[str, Any] = {
        'distinct': int(nn.nunique()),
        'min': _safe(vals[0]) if len(vals) else None,
        'max': _safe(vals[-1]) if len(vals) else None,
    }
    parsed = _try_parse_datetime(nn)
    granularity = 'unknown'
    if parsed is not None and parsed.notna().sum() >= 2:
        uniq = pd.Series(parsed.dropna().unique()).sort_values()
        span = int((uniq.max() - uniq.min()).days)
        
        
        step_days = float(uniq.diff().median().total_seconds() / 86400)
        out['span_days'] = span
        out['median_step_days'] = round(step_days, 4)
        if step_days <= 1 / 24:
            granularity = 'hour'
        elif step_days <= 1:
            granularity = 'day'
        elif step_days <= 31:
            granularity = 'month'
        else:
            granularity = 'year'
    
    if nn.astype(str).str.match(_MONTH_LABEL_RE).mean() >= _TIME_PARSE_MIN_RATIO:
        granularity = 'month'
    out['granularity'] = granularity
    return out


def _order_values(s: pd.Series) -> List[Any]:

    idx = _order_index(s)
    vals = s.dropna().tolist()
    if idx is None:
        return list(dict.fromkeys(vals))
    ordered = [vals[i] for i in idx]
    return list(dict.fromkeys(ordered))


def _order_index(s: pd.Series) -> Optional[np.ndarray]:

    if pd.api.types.is_datetime64_any_dtype(s) or pd.api.types.is_numeric_dtype(s):
        return np.argsort(s.to_numpy(), kind='stable')
    ss = s.astype(str).str.strip()
    month = ss.str.extract(_MONTH_LABEL_RE, expand=False)
    if month.notna().mean() >= _TIME_PARSE_MIN_RATIO:
        key = pd.to_numeric(month, errors='coerce')
    else:
        num = pd.to_numeric(ss, errors='coerce')
        if num.notna().mean() >= _TIME_PARSE_MIN_RATIO:
            key = num
        else:
            parsed = _try_parse_datetime(ss)
            if parsed is None or parsed.notna().mean() < _TIME_PARSE_MIN_RATIO:
                return None
            key = parsed
    try:
        return np.argsort(key.to_numpy(), kind='stable')
    except Exception:
        return None


def _group_by_type(types: Dict[str, List[str]]) -> Dict[str, List[str]]:





    return {'time': types.get('time', []),
            'category': types.get('category', []),
            'numeric': types.get('numeric', [])}




def _grain(df: pd.DataFrame) -> Dict[str, Any]:
    n = int(len(df))
    names = list(df.columns)
    
    non_numeric = [c for c in names if not pd.api.types.is_numeric_dtype(df[c])]
    singles = [str(c) for c in non_numeric if int(df[c].nunique(dropna=False)) == n and n > 0]
    pairs: List[List[str]] = []
    
    if n <= 5000 and len(names) <= 12:
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                try:
                    if int(df.groupby([names[i], names[j]], dropna=False).ngroups) == n:
                        pairs.append([str(names[i]), str(names[j])])
                except Exception:
                    continue
                if len(pairs) >= 5:
                    break
            if len(pairs) >= 5:
                break
    return {
        'row_count': n,
        'unique_keys': singles[:5],
        'unique_key_pairs': pairs,
        'note': ('存在唯一键：一行即一个实体，可直接按该键统计'
                 if (singles or pairs) else
                 '无唯一键：每行未必对应一个独立实体；当行数明显大于某维度的基数时，'
                 '绘图前必须先按该维度聚合或去重'),
    }




def _relations(df: pd.DataFrame, numeric_cols: List[str]) -> Dict[str, Any]:
    pairs = []
    cols = [c for c in numeric_cols if c in df.columns]
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            a, b = cols[i], cols[j]
            try:
                
                
                
                valid = df[[a, b]].dropna()
                if len(valid) < 3:
                    continue
                sa, sb = valid[a], valid[b]
                if float(sa.std()) == 0.0 or float(sb.std()) == 0.0:
                    continue
                r = float(sa.corr(sb))
            except Exception:
                continue
            if np.isnan(r) or abs(r) < _CORR_STRONG:
                continue
            pairs.append({'x': a, 'y': b, 'r': round(r, 4),
                          'strength': 'strong_positive' if r > 0 else 'strong_negative'})
    pairs.sort(key=lambda p: -abs(p['r']))
    return {'correlations': pairs[:10]}




def _signals(df: pd.DataFrame, types: Dict[str, List[str]],
             relations: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    by_type = _group_by_type(types)
    sig: List[Dict[str, Any]] = []
    sig += _sig_data_quality(df)
    sig += _sig_trend(df, by_type.get('time', []), by_type.get('numeric', []))
    sig += _sig_outliers(df, by_type.get('numeric', []))
    if relations is None:
        relations = _relations(df, by_type.get('numeric', []))
    sig += _sig_correlations(relations)
    sig += _sig_concentration(df, by_type.get('category', []), by_type.get('numeric', []))
    sig += _sig_divergent(df, by_type.get('time', []), by_type.get('category', []),
                          by_type.get('numeric', []))
    return sig


def _sig_data_quality(df: pd.DataFrame) -> List[Dict[str, Any]]:
    out = []
    n = int(len(df))
    if not n:
        return out
    for c in df.columns:
        s = df[c]
        miss = int(s.isna().sum())
        if miss and miss / n >= _MISSING_ALERT:
            out.append({'kind': 'missing', 'columns': [str(c)],
                        'headline': f'列「{c}」缺失率 {miss / n:.1%}（{miss}/{n}），涉及该列的结论需注明样本范围',
                        'evidence': {'missing': miss, 'rows': n, 'rate': round(miss / n, 4)}})
        card = int(s.nunique(dropna=True))
        if card <= 1 and n > 1:
            val = _safe(s.dropna().iloc[0]) if s.notna().any() else None
            out.append({'kind': 'constant', 'columns': [str(c)],
                        'headline': f'列「{c}」只有 1 个取值（{val!r}），不携带区分信息，不必作为维度',
                        'evidence': {'value': val, 'cardinality': card}})
    return out


def _sig_trend(df: pd.DataFrame, time_cols: List[str], num_cols: List[str]) -> List[Dict[str, Any]]:
    if not time_cols or not num_cols:
        return []
    t = time_cols[0]
    out = []
    for m in num_cols[:3]:
        seq = _series_by_time(df, t, m)
        if len(seq) < 3:
            continue
        first, last = float(seq.iloc[0]), float(seq.iloc[-1])
        if abs(first) < 1e-9:
            continue
        pct = (last - first) / abs(first) * 100
        direction = '上升' if pct > 0.5 else ('下降' if pct < -0.5 else '基本持平')
        
        step = seq.diff().abs().to_numpy()[1:]
        jump_i = None
        if len(step) and not np.all(np.isnan(step)):
            jump_i = int(np.nanargmax(step)) + 1
        out.append({
            'kind': 'trend', 'columns': [t, m],
            'headline': f'{m} 按 {t} 合计整体{direction}：{_f(first)} → {_f(last)}（{pct:+.1f}%）',
            'evidence': {'agg': 'sum', 'points': int(len(seq)), 'first': _f(first), 'last': _f(last),
                         'change_pct': round(pct, 2),
                         'largest_step_at': _safe(seq.index[jump_i]) if jump_i is not None else None,
                         'largest_step': _f(step[jump_i - 1]) if jump_i is not None else None},
        })
    return out


def _series_by_time(df: pd.DataFrame, t: str, m: str) -> pd.Series:

    g = df.groupby(t)[m].sum()
    idx = _order_index(pd.Series(g.index, index=range(len(g))))
    if idx is not None:
        g = g.iloc[idx]
    return g.dropna()


def _sig_outliers(df: pd.DataFrame, num_cols: List[str]) -> List[Dict[str, Any]]:
    out = []
    for c in num_cols[:5]:
        s = df[c].dropna()
        if len(s) < 4:
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = float(q3 - q1)
        if iqr <= 0:
            continue
        mask = (s < float(q1) - 1.5 * iqr) | (s > float(q3) + 1.5 * iqr)
        n_out = int(mask.sum())
        if n_out == 0:
            continue
        out.append({'kind': 'outlier', 'columns': [c],
                    'headline': f'{c} 有 {n_out} 个离群值（IQR 法），极值 {_f(s.max())} / {_f(s.min())}，与均值 {_f(s.mean())} 偏离较大',
                    'evidence': {'count': n_out, 'max': _f(s.max()), 'min': _f(s.min()),
                                 'mean': _f(s.mean()), 'q1': _f(q1), 'q3': _f(q3)}})
    return out


def _sig_correlations(relations: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for p in relations.get('correlations', [])[:3]:
        word = '强正相关' if p['r'] > 0 else '强负相关'
        out.append({'kind': 'correlation', 'columns': [p['x'], p['y']],
                    'headline': f'{p["x"]} 与 {p["y"]} {word}（r={p["r"]}）',
                    'evidence': {'r': p['r']}})
    return out


def _sig_concentration(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]) -> List[Dict[str, Any]]:
    if not cat_cols or not num_cols:
        return []
    out = []
    for c in cat_cols:
        if int(df[c].nunique(dropna=True)) > 30:
            continue
        m = num_cols[0]
        g = df.groupby(c)[m].sum().sort_values(ascending=False)
        if g.empty or float(g.sum()) == 0:
            continue
        total = float(g.sum())
        top1, top3 = g.iloc[0], g.iloc[:3].sum()
        out.append({'kind': 'concentration', 'columns': [c, m],
                    'headline': f'{m} 集中在头部：{g.index[0]} 占 {top1 / total:.1%}，前 3 个 {c} 合计占 {top3 / total:.1%}（共 {len(g)} 个）',
                    'evidence': {'agg': 'sum', 'groups': int(len(g)), 'top1': str(g.index[0]),
                                 'top1_share': round(top1 / total, 4),
                                 'top3_share': round(top3 / total, 4), 'total': _f(total)}})
    return out[:2]


def _sig_divergent(df: pd.DataFrame, time_cols: List[str], cat_cols: List[str],
                   num_cols: List[str]) -> List[Dict[str, Any]]:

    if not time_cols or not cat_cols or not num_cols:
        return []
    t = time_cols[0]
    m = num_cols[0]
    out = []
    for c in cat_cols:
        card = int(df[c].nunique(dropna=True))
        if card < 2 or card > 12:
            continue
        
        points = int(df[t].nunique(dropna=True))
        if points < 4:
            continue
        try:
            piv = df.pivot_table(index=t, columns=c, values=m, aggfunc='sum')
        except Exception:
            continue
        idx = _order_index(pd.Series(piv.index, index=range(len(piv))))
        if idx is not None:
            piv = piv.iloc[idx]
        if len(piv) < 4:
            continue
        k = max(1, len(piv) // 3)
        early, late = piv.iloc[:k].mean(), piv.iloc[-k:].mean()
        overall_e, overall_l = float(early.mean()), float(late.mean())
        if abs(overall_e) < 1e-9:
            continue
        overall_rate = (overall_l - overall_e) / abs(overall_e)
        rates = ((late - early) / early.abs().replace(0, np.nan)).dropna()
        if rates.empty:
            continue
        worst = rates.idxmin()
        worst_rate = float(rates.min())
        if worst_rate > _DIVERGE_DROP:
            continue
        if worst_rate > overall_rate - 0.15:
            continue  
        out.append({
            'kind': 'divergent_category', 'columns': [c, t, m],
            'headline': (f'{c}={worst} 逆势变化：后段较前段 {worst_rate:+.1%}，'
                         f'而同期整体 {overall_rate:+.1%}（其余 {card - 1} 个{c}平均 {(rates.drop(worst).mean()):+.1%}）'),
            'evidence': {'agg': 'sum', 'category': str(worst), 'category_change': round(worst_rate, 4),
                         'overall_change': round(overall_rate, 4),
                         'others_change': round(float(rates.drop(worst).mean()), 4),
                         'early_window': [str(x) for x in piv.index[:k]],
                         'late_window': [str(x) for x in piv.index[-k:]]},
        })
    return out[:2]




def _row_quality(df: pd.DataFrame) -> Dict[str, Any]:






    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    out: Dict[str, Any] = {'suspicious_non_data_rows': [], 'empty_rows': []}
    if not numeric_cols:
        return out
    all_num_missing = df[numeric_cols].isna().all(axis=1)
    all_cols_missing = df.isna().all(axis=1)
    for idx in df.index[all_num_missing & ~all_cols_missing]:
        row = df.loc[idx]
        sample = {str(c): _safe(row[c]) for c in df.columns if not pd.isna(row[c])}
        out['suspicious_non_data_rows'].append({'row': int(idx), 'sample': sample})
    out['empty_rows'] = [int(i) for i in df.index[all_cols_missing]]
    return out
