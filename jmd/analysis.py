"""Market analysis on top of the cleaned table (df) and the posting x skill matrix (X).

All functions are pure: they take data in and return DataFrames out, so they can
be unit-tested against the synthetic market whose true parameters are known.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import Ridge

from . import config

CONTROLS = ["role", "seniority", "city", "company_size", "remote", "source"]


# ----------------------------------------------------------------------------
# Demand
# ----------------------------------------------------------------------------
def skill_demand(X: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Per-skill posting counts, share, and raw (unadjusted) salary comparison."""
    n = len(X)
    sal = df["salary_mid_usd"]
    rows = []
    for s in X.columns:
        m = X[s].to_numpy()
        with_s, without_s = sal[m].dropna(), sal[~m].dropna()
        rows.append({
            "skill": s,
            "postings": int(m.sum()),
            "share": m.mean(),
            "n_salaried": len(with_s),
            "median_with": with_s.median() if len(with_s) else np.nan,
            "median_without": without_s.median() if len(without_s) else np.nan,
        })
    out = pd.DataFrame(rows).set_index("skill")
    out["raw_premium_pct"] = (out["median_with"] / out["median_without"] - 1) * 100
    return out.sort_values("postings", ascending=False)


def demand_by_role(X: pd.DataFrame, df: pd.DataFrame, min_n: int = 30) -> pd.DataFrame:
    """Share of postings mentioning each skill, by role family (rows=skills, cols=roles)."""
    roles = df["role"].value_counts()
    roles = roles[roles >= min_n].index
    return pd.DataFrame({r: X[df["role"].to_numpy() == r].mean() for r in roles})


def _share_by(X: pd.DataFrame, group: pd.Series, min_n: int) -> tuple[pd.DataFrame, pd.Series]:
    counts = group.value_counts()
    keep = counts[counts >= min_n].index
    shares = pd.DataFrame({g: X[(group == g).to_numpy()].mean() for g in keep})
    return shares, counts[keep]


def demand_by_city(X: pd.DataFrame, df: pd.DataFrame, min_n: int = 40) -> dict:
    """Skill share per city and the demand index (city share / overall share)."""
    shares, counts = _share_by(X, df["city"], min_n)
    overall = X.mean()
    index = shares.div(overall, axis=0).replace([np.inf], np.nan)
    return {"share": shares, "index": index, "n": counts, "overall": overall}


def demand_by_company_size(X: pd.DataFrame, df: pd.DataFrame, min_n: int = 40) -> dict:
    size = df["company_size"].astype(str).where(df["company_size"].astype(str) != "Unknown", None)
    shares, counts = _share_by(X, size, min_n)
    shares = shares[[c for c in config.COMPANY_SIZE_BUCKETS if c in shares.columns]]
    overall = X[(size != "Unknown").to_numpy()].mean()
    return {"share": shares, "index": shares.div(overall, axis=0), "n": counts, "overall": overall}


def demand_trend(X: pd.DataFrame, df: pd.DataFrame, min_month_n: int = 50, min_postings: int = 40) -> pd.DataFrame:
    """Monthly share per skill plus a growth summary: slope (share points / month) and
    ratio of the share in the last third of the window to the first third."""
    month = df["month"]
    ok = month.notna()
    counts = month[ok].value_counts()
    months = sorted(counts[counts >= min_month_n].index)
    if len(months) < 3:
        return pd.DataFrame()
    monthly = pd.DataFrame({m: X[(month == m).to_numpy()].mean() for m in months})
    monthly = monthly[X.sum() >= min_postings]
    t = np.arange(len(months))
    k = max(1, len(months) // 3)
    rows = []
    for s, row in monthly.iterrows():
        slope, intercept, r, p, se = stats.linregress(t, row.to_numpy())
        first, last = row.iloc[:k].mean(), row.iloc[-k:].mean()
        rows.append({"skill": s, "share_first": first, "share_last": last, "growth_ratio": (last / first) if first > 0 else np.nan,
                     "slope_pp_per_month": slope * 100, "p_value": p, "postings": int(X[s].sum())})
    summary = pd.DataFrame(rows).set_index("skill")
    summary.attrs["monthly"] = monthly
    return summary.sort_values("growth_ratio", ascending=False)


# ----------------------------------------------------------------------------
# Pay
# ----------------------------------------------------------------------------
def adjusted_premiums(X: pd.DataFrame, df: pd.DataFrame, min_support: int = config.MIN_SUPPORT_FOR_PREMIUM,
                      n_boot: int = 200, alpha: float = 1.0, seed: int = 0) -> pd.DataFrame:
    """Skill salary premiums holding role, seniority, city, company size, remote and source constant.

    Fits log(salary_mid) ~ controls + skill indicators with a ridge penalty (skills are
    highly collinear). A coefficient b means "a posting that lists this skill pays
    exp(b)-1 more than an otherwise identical posting". Bootstrap resampling of
    postings gives 95% intervals.
    """
    mask = df["salary_mid_usd"].notna().to_numpy()
    y = np.log(df.loc[mask, "salary_mid_usd"].to_numpy())
    skills = [s for s in X.columns if X.loc[mask, s].sum() >= min_support]
    S = X.loc[mask, skills].astype(float)
    C = pd.get_dummies(df.loc[mask, CONTROLS].astype(str), drop_first=True).astype(float)
    Z = pd.concat([C.reset_index(drop=True), S.reset_index(drop=True)], axis=1).to_numpy()
    n_controls = C.shape[1]

    def fit(idx):
        m = Ridge(alpha=alpha).fit(Z[idx], y[idx])
        return m.coef_[n_controls:]

    base = fit(np.arange(len(y)))
    rng = np.random.default_rng(seed)
    boots = np.array([fit(rng.integers(0, len(y), len(y))) for _ in range(n_boot)])
    lo, hi = np.percentile(boots, [2.5, 97.5], axis=0)
    out = pd.DataFrame({"skill": skills, "coef": base, "premium_pct": (np.exp(base) - 1) * 100,
                        "ci_lo_pct": (np.exp(lo) - 1) * 100, "ci_hi_pct": (np.exp(hi) - 1) * 100,
                        "n_salaried": S.sum().to_numpy().astype(int)}).set_index("skill")
    out["significant"] = (out["ci_lo_pct"] > 0) | (out["ci_hi_pct"] < 0)
    out.attrs["n_obs"] = int(mask.sum())
    out.attrs["r2"] = float(Ridge(alpha=alpha).fit(Z, y).score(Z, y))
    return out.sort_values("premium_pct", ascending=False)


def salary_by(df: pd.DataFrame, col: str, min_n: int = 20) -> pd.DataFrame:
    g = df.dropna(subset=["salary_mid_usd"]).groupby(col, observed=True)["salary_mid_usd"]
    out = g.agg(n="size", median="median", p25=lambda s: s.quantile(.25), p75=lambda s: s.quantile(.75))
    return out[out["n"] >= min_n].sort_values("median", ascending=False)


# ----------------------------------------------------------------------------
# Combinations
# ----------------------------------------------------------------------------
def cooccurrence(X: pd.DataFrame, min_pair: int = 10) -> pd.DataFrame:
    """Pairwise co-occurrence with support, lift and Jaccard, for every pair seen >= min_pair times."""
    M = X.astype(int).to_numpy()
    n = len(M)
    counts = M.T @ M
    single = np.diag(counts)
    rows = []
    for i, j in combinations(range(len(X.columns)), 2):
        both = counts[i, j]
        if both < min_pair:
            continue
        expected = single[i] * single[j] / n
        rows.append({"a": X.columns[i], "b": X.columns[j], "both": int(both), "share": both / n,
                     "lift": both / expected if expected else np.nan,
                     "jaccard": both / (single[i] + single[j] - both)})
    return pd.DataFrame(rows).sort_values("lift", ascending=False).reset_index(drop=True)


def lift_matrix(X: pd.DataFrame, skills: list[str]) -> pd.DataFrame:
    M = X[skills].astype(int).to_numpy()
    n = len(M)
    counts = M.T @ M
    p = np.diag(counts) / n
    with np.errstate(divide="ignore", invalid="ignore"):
        L = (counts / n) / np.outer(p, p)
    L[~np.isfinite(L)] = np.nan
    return pd.DataFrame(L, index=skills, columns=skills)


def control_residuals(df: pd.DataFrame, alpha: float = 1.0) -> pd.Series:
    """log(salary) minus what role, seniority, city, company size, remote and source alone predict.

    A positive residual means the posting pays more than a typical posting of its kind.
    NaN where no salary is known.
    """
    mask = df["salary_mid_usd"].notna().to_numpy()
    y = np.log(df.loc[mask, "salary_mid_usd"].to_numpy())
    C = pd.get_dummies(df.loc[mask, CONTROLS].astype(str), drop_first=True).astype(float).to_numpy()
    resid = y - Ridge(alpha=alpha).fit(C, y).predict(C)
    out = pd.Series(np.nan, index=df.index, dtype=float)
    out[mask] = resid
    return out


def rare_valuable_combos(X: pd.DataFrame, df: pd.DataFrame, max_share: float = 0.03, min_pair: int = 15,
                         min_salaried: int = 10) -> pd.DataFrame:
    """Skill pairs that are rare (appear in <= max_share of postings) but pay well.

    Pay is measured on salary *residuals* after role, seniority, city, company size,
    remote and source (see `control_residuals`), so a pair does not score just because
    it is typical of a well-paid role. `premium_vs_either_pct` compares the mean
    residual of postings with BOTH skills to the better of the two single-skill means:
    a combo only scores when it adds something over its parts.
    """
    pairs = cooccurrence(X, min_pair=min_pair)
    pairs = pairs[pairs["share"] <= max_share]
    sal = df["salary_mid_usd"]
    resid = control_residuals(df)
    rows = []
    for r in pairs.itertuples():
        a, b = X[r.a].to_numpy(), X[r.b].to_numpy()
        m = a & b
        both = resid[m].dropna()
        if len(both) < min_salaried:
            continue
        r_a, r_b = resid[a & ~b].mean(), resid[b & ~a].mean()
        best_single = np.nanmax([r_a, r_b, 0.0]) if np.isfinite([r_a, r_b]).any() else 0.0
        rows.append({"a": r.a, "b": r.b, "postings": r.both, "share": r.share, "lift": r.lift, "n_salaried": len(both),
                     "median_both": sal[m].median(),
                     "premium_vs_similar_pct": (np.exp(both.mean()) - 1) * 100,
                     "premium_vs_either_pct": (np.exp(both.mean() - best_single) - 1) * 100,
                     "t_stat": both.mean() / (both.std(ddof=1) / np.sqrt(len(both))) if len(both) > 2 and both.std(ddof=1) > 0 else np.nan})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("premium_vs_either_pct", ascending=False).reset_index(drop=True)


def frequent_triples(X: pd.DataFrame, top_skills: int = 30, min_support: float = 0.02, top: int = 25) -> pd.DataFrame:
    """Most common 3-skill bundles among the most frequent skills (an Apriori-style pass)."""
    cols = X.sum().sort_values(ascending=False).head(top_skills).index
    M = X[cols].to_numpy()
    n = len(M)
    rows = []
    for i, j, k in combinations(range(len(cols)), 3):
        c = int((M[:, i] & M[:, j] & M[:, k]).sum())
        if c / n >= min_support:
            rows.append({"skills": f"{cols[i]} + {cols[j]} + {cols[k]}", "postings": c, "share": c / n})
    return pd.DataFrame(rows).sort_values("postings", ascending=False).head(top).reset_index(drop=True)
