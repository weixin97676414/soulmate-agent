#!/usr/bin/env python3
# -*- coding: utf-8 -*-








from __future__ import annotations

import numpy as np




def km_estimate(times, events):






    t = np.asarray(times, dtype=float)
    e = np.asarray(events, dtype=float)
    if t.ndim != 1 or e.ndim != 1 or len(t) != len(e):
        raise ValueError("km: times/events 必须是等长一维数值序列")
    if len(t) == 0:
        raise ValueError("km: 数据为空")
    if np.any(~np.isfinite(t)) or np.any(~np.isfinite(e)):
        raise ValueError("km: 含 NaN/Inf 值")
    if np.any(t < 0):
        raise ValueError("km: 存在负时间")
    if np.any((e != 0) & (e != 1)):
        raise ValueError("km: event 必须是 0（删失）或 1（事件）")
    order = np.argsort(t, kind="stable")
    t, e = t[order], e[order]
    ut, first_idx, counts = np.unique(t, return_index=True, return_counts=True)
    d = np.add.reduceat(e, first_idx)                     
    n_at_risk = len(t) - np.concatenate(([0], np.cumsum(counts)[:-1]))
    has_event = d > 0
    surv_steps = np.ones(len(ut))
    surv_steps[has_event] = 1.0 - d[has_event] / n_at_risk[has_event]
    surv = np.cumprod(surv_steps)
    t_seq = np.concatenate(([0.0], ut))
    s_seq = np.concatenate(([1.0], surv))
    censor_mask = counts > d
    censor_points = list(zip(ut[censor_mask].tolist(), surv[censor_mask].tolist()))
    return t_seq, s_seq, censor_points


def km_at_risk(times, events, eval_times):

    t = np.asarray(times, dtype=float)
    return [int(np.sum(t >= float(et))) for et in eval_times]


def default_risk_times(all_times, k=5):

    tmax = float(np.max(all_times)) if len(all_times) else 0.0
    if tmax <= 0:
        return [0.0]
    step = tmax / (k - 1)
    return [round(step * i, 6) for i in range(k)]


def logrank_test(groups):






    from scipy import stats as _st
    clean = {}
    for name, (t, e) in groups.items():
        t = np.asarray(t, dtype=float)
        e = np.asarray(e, dtype=float)
        if len(t) == 0:
            continue
        if len(t) != len(e):
            raise ValueError("log-rank: 组内 times/events 等长")
        order = np.argsort(t, kind="stable")
        clean[name] = (t[order], e[order])
    names = list(clean.keys())
    if len(names) < 2:
        raise ValueError("log-rank 需要 >=2 组")
    k = len(names)
    n_total_all = sum(len(a[0]) for a in clean.values())
    if n_total_all < 2:
        raise ValueError("log-rank: 总样本 <2")
    
    event_only = [a[0][a[1] == 1] for a in clean.values()]
    event_times = np.unique(np.concatenate(event_only)) if event_only else np.array([])
    
    Ns = np.array([len(a[0]) for a in clean.values()], dtype=float)
    ev_times_arr, ev_counts_arr = [], []
    for g in range(k):
        et, cnt = np.unique(clean[names[g]][0][clean[names[g]][1] == 1],
                            return_counts=True)
        ev_times_arr.append(et)
        ev_counts_arr.append(cnt)
    O = np.zeros(k)
    E = np.zeros(k)
    V_sum = np.zeros((k, k))
    for ut in event_times:
        n_g = np.array([Ns[g] - np.searchsorted(clean[names[g]][0], ut, side="left")
                        for g in range(k)], dtype=float)
        n_total = n_g.sum()
        if n_total < 2:
            continue
        d_g = np.zeros(k)
        for g in range(k):
            pos = np.searchsorted(ev_times_arr[g], ut)
            if pos < len(ev_times_arr[g]) and ev_times_arr[g][pos] == ut:
                d_g[g] = ev_counts_arr[g][pos]
        d_total = d_g.sum()
        if d_total <= 0:
            continue
        O += d_g
        E += n_g * d_total / n_total
        coef = d_total * (n_total - d_total) / (n_total * n_total * (n_total - 1))
        
        V_sum += coef * (np.diag(n_g * (n_total - n_g) + n_g * n_g) - np.outer(n_g, n_g))
    
    diff = (O - E)[:-1]
    Vr = V_sum[:-1, :-1]
    chi2 = float(diff @ np.linalg.pinv(Vr) @ diff) if np.trace(Vr) > 0 else 0.0
    df = len(names) - 1
    return chi2, float(_st.chi2.sf(chi2, df)), df




def dl_pool(effects, ses):





    from scipy import stats as _st
    es = np.asarray(effects, dtype=float)
    se = np.asarray(ses, dtype=float)
    if len(es) < 2:
        raise ValueError("meta 合并需要 >=2 个研究")
    if np.any(se <= 0) or np.any(~np.isfinite(se)) or np.any(~np.isfinite(es)):
        raise ValueError("meta: se 必须为正且效应值/标准误均为有限数值")
    w = 1.0 / se ** 2
    fe = float(np.sum(w * es) / np.sum(w))
    q = float(np.sum(w * (es - fe) ** 2))
    df = len(es) - 1
    c = float(np.sum(w) - np.sum(w ** 2) / np.sum(w))
    tau2 = max(0.0, (q - df) / c) if c > 0 else 0.0
    w_re = 1.0 / (se ** 2 + tau2)
    pooled = float(np.sum(w_re * es) / np.sum(w_re))
    se_pooled = float(1.0 / np.sqrt(np.sum(w_re)))
    i2 = max(0.0, (q - df) / q) * 100.0 if q > 0 else 0.0
    p_het = float(_st.chi2.sf(q, df))
    return {"pooled": pooled, "se": se_pooled, "q": q, "df": df,
            "p_het": p_het, "i2": i2, "tau2": tau2}


def egger_test(effects, ses):





    from scipy import stats as _st
    es = np.asarray(effects, dtype=float)
    se = np.asarray(ses, dtype=float)
    if len(es) < 3:
        raise ValueError("egger 检验需要 >=3 个研究")
    if np.any(se <= 0):
        raise ValueError("egger: se 必须为正")
    precision = 1.0 / se
    z = es / se
    res = _st.linregress(precision, z)
    return {"intercept": float(res.intercept), "p": float(res.pvalue),
            "slope": float(res.slope)}




def hochberg(pvals):

    p = np.asarray(pvals, dtype=float)
    n = len(p)
    if n == 0:
        return p
    order = np.argsort(p)
    adj_sorted = np.empty(n)
    running = 1.0
    for rank_from_top, idx in enumerate(order[::-1]):
        multiplier = n - rank_from_top
        running = min(running, multiplier * p[idx])
        adj_sorted[idx] = min(1.0, running)
    return adj_sorted


def _mse_and_df(groups_vals):

    k = len(groups_vals)
    n_total = sum(len(g) for g in groups_vals)
    grand = np.mean(np.concatenate(groups_vals))
    sse = sum(float(np.sum((np.asarray(g) - np.mean(g)) ** 2)) for g in groups_vals)
    return sse / (n_total - k), n_total - k


def tukey_pairs(series):




    from scipy import stats as _st
    names = list(series.keys())
    k = len(names)
    if k < 2:
        raise ValueError("Tukey 需要 >=2 组")
    vals = [np.asarray(series[n], dtype=float) for n in names]
    means = [float(np.mean(v)) for v in vals]
    ns = [len(v) for v in vals]
    mse, df = _mse_and_df(vals)
    out = []
    for i in range(k):
        for j in range(i + 1, k):
            q = abs(means[i] - means[j]) / np.sqrt(mse / 2.0 * (1.0 / ns[i] + 1.0 / ns[j]))
            p = float(_st.studentized_range.sf(q, k, df)) if mse > 0 else 1.0
            out.append((names[i], names[j], p, _stars(p), "Tukey HSD"))
    return out


def dunn_pairs(series):



    from scipy import stats as _st
    names = list(series.keys())
    vals = [np.asarray(series[n], dtype=float) for n in names]
    all_v = np.concatenate(vals)
    n_total = len(all_v)
    if n_total < 3:
        raise ValueError("Dunn 需要总样本 >=3")
    
    order = np.argsort(all_v, kind="stable")
    ranks_sorted = np.empty(n_total)
    i = 0
    sorted_v = all_v[order]
    while i < n_total:
        j = i
        while j < n_total and sorted_v[j] == sorted_v[i]:
            j += 1
        ranks_sorted[i:j] = 0.5 * (i + j - 1) + 1.0
        i = j
    ranks = np.empty(n_total)
    ranks[order] = ranks_sorted          
    pos = 0
    rank_means, rank_sums = {}, {}
    for name, v in zip(names, vals):
        n_i = len(v)
        seg = ranks[pos:pos + n_i]
        rank_sums[name] = float(seg.sum())
        rank_means[name] = float(seg.mean())
        pos += n_i
    
    _, tie_counts = np.unique(all_v, return_counts=True)
    tie_term = float(np.sum(tie_counts ** 3 - tie_counts))
    sigma2 = (n_total * (n_total + 1) / 12.0) - tie_term / (12.0 * (n_total - 1)) \
        if n_total > 1 else 0.0
    out = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            ni, nj = len(vals[i]), len(vals[j])
            if ni == 0 or nj == 0:
                continue
            se = np.sqrt(max(sigma2, 0.0) * (1.0 / ni + 1.0 / nj))
            z = abs(rank_means[names[i]] - rank_means[names[j]]) / se if se > 0 else 0.0
            p = float(2.0 * _st.norm.sf(z))
            out.append((names[i], names[j], p, _stars(p), "Dunn"))
    return out


def multi_pairwise(series):



    from scipy import stats as _st
    names = list(series.keys())
    if len(names) < 2:
        raise ValueError("多组比较需要 >=2 组")
    vals = {}
    for n in names:
        v = np.asarray(series[n], dtype=float)
        v = v[np.isfinite(v)]
        vals[n] = v
    vals = {n: v for n, v in vals.items() if len(v) >= 1}
    if len(vals) < 2:
        raise ValueError("有效组不足 2 组")
    all_normal = True
    for v in vals.values():
        if 3 <= len(v) <= 5000:
            if float(_st.shapiro(v).pvalue) <= 0.05:
                all_normal = False
                break
        elif len(v) > 5000:
            continue  
        else:
            all_normal = False
            break
    if all_normal:
        pairs = tukey_pairs(vals)
    else:
        pairs = dunn_pairs(vals)
        if not pairs:
            return pairs
        ps = np.array([p for _, _, p, _, _ in pairs])
        adj = hochberg(ps)
        pairs = [(a, b, float(ap), _stars(float(ap)), m + "+Hochberg")
                 for (a, b, p, _, m), ap in zip(pairs, adj)]
    return pairs


def _stars(p):
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "n.s."





def km_median_survival(times, events, alpha=0.05):







    from scipy import stats as _st
    t = np.asarray(times, dtype=float)
    e = np.asarray(events, dtype=float)
    if len(t) == 0:
        raise ValueError("km: 数据为空")
    order = np.argsort(t, kind="stable")
    t, e = t[order], e[order]
    ut, first_idx, counts = np.unique(t, return_index=True, return_counts=True)
    d = np.add.reduceat(e, first_idx)
    n_risk = len(t) - np.concatenate(([0], np.cumsum(counts)[:-1]))
    has_event = d > 0
    
    surv_steps = np.ones(len(ut))
    surv_steps[has_event] = 1.0 - d[has_event] / n_risk[has_event]
    surv = np.cumprod(surv_steps)
    with np.errstate(divide="ignore", invalid="ignore"):
        var_term = np.where(has_event & (n_risk > d),
                            d / (n_risk * (n_risk - d)), 0.0)
    gvar = np.cumsum(var_term)
    z = float(_st.norm.ppf(1 - alpha / 2))

    def _cross(env):

        idx = np.where(env <= 0.5)[0]
        return float(ut[idx[0]]) if len(idx) else None

    def _cross_interp(ut_arr, surv_arr, env):

        env_arr = np.full(len(surv_arr), env, dtype=float) if np.isscalar(env) else np.asarray(env, dtype=float)
        idx = np.where(surv_arr[1:] <= env_arr[1:])[0]
        if not len(idx):
            return None
        k = idx[0] + 1  
        s_prev, s_cur = surv_arr[k - 1], surv_arr[k]
        t_prev, t_cur = ut_arr[k - 1], ut_arr[k]
        if s_cur == s_prev:
            return float(t_cur)
        frac = (s_prev - env_arr[k]) / (s_prev - s_cur)
        return float(t_prev + (t_cur - t_prev) * frac)

    below = np.where(surv <= 0.5)[0]
    if not len(below):
        return None, None, None
    med = float(ut[below[0]])
    
    
    safe_log = np.where((surv > 0) & (surv < 1), np.abs(np.log(np.where(surv > 0, surv, 0.5))), 1.0)
    sigma = np.where((surv < 1.0) & (surv > 0.0), np.sqrt(gvar) / safe_log, 0.0)
    lo_env = np.power(surv, np.exp(+np.minimum(z * sigma, 50)))  
    hi_env = np.power(surv, np.exp(-np.minimum(z * sigma, 50)))  
    
    ci_lo = _cross(lo_env)
    ci_hi = _cross(hi_env)
    return med, ci_lo, ci_hi


def _m_sqrt(x):
    return float(np.sqrt(x))


def _m_log(x):
    return float(np.log(x))


def _m_exp(x):
    return float(np.exp(x))


def _m_sqrt(x):
    return float(np.sqrt(x))


def _m_log(x):
    return float(np.log(x))


def _m_exp(x):
    return float(np.exp(x))


def leave_one_out(es, ses):





    es = list(es)
    ses = list(ses)
    n = len(es)
    if n < 4:
        raise ValueError("留一法需要 >=4 个研究（太少无敏感性意义）")
    out = []
    for i in range(n):
        sub_e = [es[k] for k in range(n) if k != i]
        sub_s = [ses[k] for k in range(n) if k != i]
        r = dl_pool(sub_e, sub_s)
        out.append((i, r["pooled"],
                    r["pooled"] - 1.96 * r["se"], r["pooled"] + 1.96 * r["se"]))
    return out



def _midrank(x):
    x = np.asarray(x, dtype=float)
    order = np.argsort(x, kind="stable")
    xs = x[order]
    n = len(x)
    t = np.empty(n)
    i = 0
    while i < n:
        j = i
        while j < n and xs[j] == xs[i]:
            j += 1
        t[i:j] = 0.5 * (i + j - 1) + 1.0
        i = j
    out = np.empty(n)
    out[order] = t
    return out


def delong_paired(labels, scores_by_model):





    from scipy import stats as _st
    y = np.asarray(labels, dtype=float)
    if len(y) == 0 or np.any(~np.isin(y, (0.0, 1.0))):
        raise ValueError("DeLong: labels 必须是 0/1 数组")
    m_pos = int(np.sum(y == 1))
    n_neg = int(np.sum(y == 0))
    if m_pos == 0 or n_neg == 0:
        raise ValueError("DeLong: 需要同时包含阳性和阴性样本")
    names = list(scores_by_model.keys())
    tz_at_pos, tx_pos, tz_at_neg, ty_neg, aucs = [], [], [], [], {}
    for name in names:
        s = np.asarray(scores_by_model[name], dtype=float)
        if len(s) != len(y) or np.any(~np.isfinite(s)):
            raise ValueError(f"DeLong: 模型 {name} 的分数与 labels 等长且为有限数值")
        z = _midrank(s)                 
        tx = _midrank(s[y == 1])        
        ty = _midrank(s[y == 0])        
        tz_at_pos.append(z[y == 1])
        tx_pos.append(tx)
        tz_at_neg.append(z[y == 0])
        ty_neg.append(ty)
        
        aucs[name] = float(np.mean((z[y == 1] - tx) / n_neg))
    k = len(names)
    
    v01 = np.empty((k, m_pos))
    v10 = np.empty((k, n_neg))
    for r, name in enumerate(names):
        v01[r] = (tz_at_pos[r] - tx_pos[r]) / n_neg
        v10[r] = (tz_at_neg[r] - ty_neg[r]) / m_pos
    sx = np.cov(v01) if m_pos > 1 else np.zeros((k, k))
    sy = np.cov(v10) if n_neg > 1 else np.zeros((k, k))
    sigma = sx / m_pos + sy / n_neg
    pairs = []
    for i in range(k):
        for j in range(i + 1, k):
            var = sigma[i, i] + sigma[j, j] - 2.0 * sigma[i, j]
            if var <= 0:
                p, z = 1.0, 0.0
            else:
                z = abs(aucs[names[i]] - aucs[names[j]]) / np.sqrt(var)
                p = float(2.0 * _st.norm.sf(z))
            pairs.append((names[i], names[j], p, float(z)))
    return aucs, pairs




def _cox_efron(beta, t, e, X, ev_times):


    p = X.shape[1]
    eta = X @ beta
    shift = eta.max() if eta.size else 0.0
    w = np.exp(eta - shift)
    ll = 0.0
    grad = np.zeros(p)
    info = np.zeros((p, p))
    for te, i0 in ev_times:
        th = w[i0:]
        xR = X[i0:]
        S0 = th.sum()
        S1 = th @ xR
        S2 = (xR * th[:, None]).T @ xR
        is_ev = (t[i0:] == te) & (e[i0:] == 1)
        if not is_ev.any():
            continue
        thD = th[is_ev]
        xD = xR[is_ev]
        d = int(is_ev.sum())
        D0 = thD.sum()
        D1 = thD @ xD
        D2 = (xD * thD[:, None]).T @ xD
        ll += float(np.log(thD).sum())
        grad += xD.sum(axis=0)  
        for l in range(d):
            f = l / d
            Z0 = S0 - f * D0
            Z1 = S1 - f * D1
            Z2 = S2 - f * D2
            ll -= float(np.log(Z0))
            grad -= Z1 / Z0
            info += Z2 / Z0 - np.outer(Z1, Z1) / (Z0 * Z0)
    return ll, grad, info


def coxph_fit(times, events, cov, names=None, tol=1e-10, max_iter=60):





    import math
    t = np.asarray(times, dtype=float)
    e = np.asarray(events, dtype=float)
    X = np.asarray(cov, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    n, p = X.shape
    if names is None:
        names = [f"x{k + 1}" for k in range(p)]
    names = [str(x) for x in names]
    if not (len(t) == len(e) == n):
        raise ValueError(f"time/event/协变量行数不一致：{len(t)}/{len(e)}/{n}")
    if n < 10:
        raise ValueError(f"样本量过小（n={n}）：Cox 回归至少需要约 10 例（建议 ≥10×每协变量）")
    if (t <= 0).any():
        raise ValueError("time 存在非正数——生存时间必须 >0")
    if not np.isin(e, (0, 1)).all():
        raise ValueError("event 必须为 0/1（0=删失，1=事件）")
    if not np.isfinite(X).all():
        bad = np.argwhere(~np.isfinite(X))
        raise ValueError(f"协变量含 NaN/Inf（共 {len(bad)} 处，如第 {bad[0][0] + 1} 行"
                         f"第 {names[bad[0][1]]} 列）——请先清洗缺失值")
    sd = X.std(axis=0)
    if (sd == 0).any():
        bad = [names[k] for k in np.where(sd == 0)[0]]
        raise ValueError(f"协变量为常数列（无变异）：{ '、'.join(bad) }——请移除后重试")
    mu = X.mean(axis=0)
    Xs = (X - mu) / sd

    order = np.argsort(t, kind="mergesort")
    t, e, Xs = t[order], e[order], Xs[order]
    ev_times = [(float(tv), int(np.searchsorted(t, tv, side="left")))
                for tv in np.unique(t[e == 1])]

    beta = np.zeros(p)
    converged = False
    it = 0
    for it in range(1, max_iter + 1):
        ll, grad, info = _cox_efron(beta, t, e, Xs, ev_times)
        try:
            step = np.linalg.solve(info, grad)
        except np.linalg.LinAlgError:
            raise ValueError("信息矩阵奇异（协变量间可能完全共线）——"
                             "请检查并移除线性相关的协变量")
        f = 1.0
        while f > 1e-8:
            b2 = beta + f * step
            ll2, _, _ = _cox_efron(b2, t, e, Xs, ev_times)
            if ll2 >= ll - 1e-10:
                break
            f /= 2
        if np.max(np.abs(f * step)) < tol:
            converged = True
            break
        beta = beta + f * step
    if not converged:
        ll, grad, info = _cox_efron(beta, t, e, Xs, ev_times)
        print(f"WARNING: Cox 牛顿迭代 {max_iter} 次未完全收敛（可能共线或数据极端），"
              f"结果仅供参考", file=sys.stderr)

    info_s = info
    cov_s = np.linalg.inv(info_s)
    se_s = np.sqrt(np.diag(cov_s))
    beta_raw = beta / sd
    se_raw = se_s / sd
    z = beta_raw / se_raw
    pvals = np.array([math.erfc(abs(zz) / math.sqrt(2)) for zz in z])
    hr = np.exp(beta_raw)
    zq = 1.959963984540054  
    return {
        "names": names, "beta": beta_raw, "se": se_raw, "z": z, "p": pvals,
        "hr": hr, "hr_low": np.exp(beta_raw - zq * se_raw),
        "hr_high": np.exp(beta_raw + zq * se_raw),
        "n": int(n), "n_events": int(e.sum()),
        "loglik": float(ll), "iterations": it, "converged": converged,
        "info": info_s,
        "_state": (t, e, Xs),
    }


def cox_ph_test(fit):



    import math
    t, e, Xs = fit["_state"]
    sd = Xs.std(axis=0)
    
    beta_s = fit["beta"] * sd
    info_s = fit["info"]
    p = Xs.shape[1]
    ev_idx = np.where(e == 1)[0]
    if len(ev_idx) < p + 5:
        return {"names": fit["names"], "p": np.full(p, np.nan), "z": np.zeros(p)}
    d = len(ev_idx)
    inv_info = np.linalg.inv(info_s)
    r_scaled = np.empty((d, p))
    t_ev = np.empty(d)
    for k, i in enumerate(ev_idx):
        te = t[i]
        i0 = int(np.searchsorted(t, te, side="left"))
        th = np.exp(Xs[i0:] @ beta_s)
        wmean = (th @ Xs[i0:]) / th.sum()
        r_scaled[k] = d * (inv_info @ (Xs[i] - wmean)) + beta_s
        t_ev[k] = te
    g = np.log(t_ev)
    gc = g - g.mean()
    denom = (gc ** 2).sum()
    names, ps, zs = fit["names"], [], []
    for k in range(p):
        rk = r_scaled[:, k]
        slope = (gc * (rk - rk.mean())).sum() / denom
        resid = rk - rk.mean() - slope * gc
        s2 = (resid ** 2).sum() / max(len(g) - 2, 1)
        se = math.sqrt(s2 / denom)
        z = slope / se if se > 0 else 0.0
        zs.append(z)
        ps.append(math.erfc(abs(z) / math.sqrt(2)))
    return {"names": names, "p": np.array(ps), "z": np.array(zs)}





BOOT_N_DEFAULT = 5000


def bootstrap_ci(values, statistic=None, n_boot=None, seed=20260925):





    import numpy as np
    vals = np.asarray([float(v) for v in values if v is not None], dtype=float)
    vals = vals[np.isfinite(vals)]
    if vals.size < 2:
        raise ValueError("bootstrap: 每组至少需要 2 个有效数值")
    stat_fn = statistic if statistic is not None else np.mean
    n_boot = int(n_boot or BOOT_N_DEFAULT)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, vals.size, size=(n_boot, vals.size))
    stats = stat_fn(vals[idx], axis=1)
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return float(stat_fn(vals)), float(lo), float(hi)


def bootstrap_vs_first(series, n_boot=None, seed=20260925):




    import numpy as np
    names = list(series.keys())
    if len(names) < 2:
        return []
    first = np.asarray([float(v) for v in series[names[0]] if v is not None], dtype=float)
    out = []
    base_seed = int(seed)
    for i, name in enumerate(names[1:], 1):
        other = np.asarray([float(v) for v in series[name] if v is not None], dtype=float)
        n_min = min(first.size, other.size)
        if n_min < 2 or first.size == 0 or other.size == 0:
            out.append((name, None, None, None))
            continue
        rng = np.random.default_rng(base_seed + i)
        
        n_boot_i = int(n_boot or BOOT_N_DEFAULT)
        idx_f = rng.integers(0, first.size, size=(n_boot_i, first.size))
        idx_o = rng.integers(0, other.size, size=(n_boot_i, other.size))
        stats = other[idx_o].mean(axis=1) - first[idx_f].mean(axis=1)
        lo, hi = np.percentile(stats, [2.5, 97.5])
        out.append((name, float(other.mean() - first.mean()), float(lo), float(hi)))
    return out






def aalen_johansen(times, events, eval_times=None):














    import numpy as np
    t = np.asarray([float(v) for v in times], dtype=float)
    e = np.asarray([int(v) for v in events], dtype=int)
    if t.size != e.size or t.size == 0:
        raise ValueError("aalen_johansen: times/events 需同长非空")
    if np.any(np.isnan(t)) or np.any(e < 0):
        raise ValueError("aalen_johansen: 时间不可为 NaN，事件编码需 ≥0")

    order = np.argsort(t, kind="stable")
    t, e = t[order], e[order]
    uniq = np.unique(t)
    states = sorted(set(int(x) for x in e if x >= 1))
    if not states:
        raise ValueError("aalen_johansen: 无事件（全删失）——无法估计累计发生率")

    surv = 1.0
    cif = {j: 0.0 for j in states}
    out_t, out_s = [], []
    out_cif = {j: [] for j in states}

    for tk in uniq:
        at_risk = int((t >= tk).sum())
        if at_risk == 0:
            continue
        d_all = int(((t == tk) & (e >= 1)).sum())
        s_before = surv  
        if d_all > 0:
            surv *= 1.0 - d_all / at_risk
        for j in states:
            d_j = int(((t == tk) & (e == j)).sum())
            if d_j > 0:
                cif[j] += s_before * d_j / at_risk
        out_t.append(float(tk))
        out_s.append(surv)
        for j in states:
            out_cif[j].append(cif[j])

    if eval_times is not None:
        et = [float(v) for v in eval_times]

        def _step(steps, values, q):
            cur = 0.0 if not steps else values[0] * 0 + (values[0] if steps[0] <= q else (0.0 if steps[0] > q else values[0]))
            cur = 0.0
            for st, val in zip(steps, values):
                if st <= q + 1e-12:
                    cur = val
                else:
                    break
            return cur

        res_t = [float(v) for v in et]
        res_s = [_step(out_t, out_s, q) for q in et]
        res_cif = {j: [_step(out_t, out_cif[j], q) for q in et] for j in states}
        return {"times": res_t, "survival": res_s, "cif": res_cif}
    return {"times": out_t, "survival": out_s, "cif": out_cif}


def _aj_step(steps, values, q):

    cur = 0.0
    for st, val in zip(steps, values):
        if st <= q + 1e-12:
            cur = val
        else:
            break
    return cur


def bootstrap_median_ci(values, n_boot=None, seed=20260925):



    import numpy as np
    vals = np.asarray([float(v) for v in values if v is not None], dtype=float)
    vals = vals[np.isfinite(vals)]
    if vals.size < 2:
        raise ValueError("bootstrap_median_ci: 每组至少需要 2 个有效数值")
    n_boot = int(n_boot or BOOT_N_DEFAULT)
    rng = np.random.default_rng(int(seed) + 1)  
    med = float(np.median(vals))
    idx = rng.integers(0, vals.size, size=(n_boot, vals.size))
    meds = np.median(vals[idx], axis=1)
    lo, hi = np.percentile(meds, [2.5, 97.5])
    return med, float(lo), float(hi)
