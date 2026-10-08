"""Figures and the Markdown report.

Chart conventions (kept deliberately plain): one hue for magnitude, blue/red
with a grey midpoint for "above/below baseline", fixed categorical order for
series, thin marks, recessive grid, direct labels where they help.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402

from . import config  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
BLUE, RED, GREY_MID = "#2a78d6", "#e34948", "#f0efec"
SEQ = LinearSegmentedColormap.from_list("seq_blue", ["#fcfcfb", "#cde2fb", "#6da7ec", "#2a78d6", "#184f95", "#0d366b"])
DIV = LinearSegmentedColormap.from_list("div_blue_red", ["#104281", "#2a78d6", "#9ec5f4", GREY_MID, "#f4a3a3", "#e34948", "#9c1d1d"])
TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e1"

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "axes.edgecolor": GRID, "axes.labelcolor": TEXT,
    "xtick.color": MUTED, "ytick.color": MUTED, "text.color": TEXT, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "legend.frameon": False, "savefig.dpi": 150, "savefig.bbox": "tight",
})


def _save(fig, name: str, outdir: Path) -> Path:
    path = outdir / name
    fig.savefig(path)
    plt.close(fig)
    return path


# ----------------------------------------------------------------------------
def fig_top_skills(demand: pd.DataFrame, outdir: Path, top: int = 25) -> Path:
    d = demand.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 0.32 * top + 1))
    ax.barh(d.index, d["share"] * 100, color=BLUE, height=0.62)
    for i, v in enumerate(d["share"] * 100):
        ax.text(v + 0.6, i, f"{v:.0f}%", va="center", fontsize=8.5, color=MUTED)
    ax.set_xlabel("Share of data-role postings mentioning the skill")
    ax.set_title(f"Most requested skills (top {top})")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.grid(axis="y", visible=False)
    return _save(fig, "01_top_skills.png", outdir)


def fig_premiums(prem: pd.DataFrame, outdir: Path, n_pos: int = 15, n_neg: int = 8) -> Path:
    p = prem[prem["n_salaried"] >= config.MIN_SUPPORT_FOR_PREMIUM]
    sel = pd.concat([p.head(n_pos), p.tail(n_neg)]).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 0.34 * len(sel) + 1.2))
    y = np.arange(len(sel))
    colors = [BLUE if v >= 0 else RED for v in sel["premium_pct"]]
    ax.hlines(y, sel["ci_lo_pct"], sel["ci_hi_pct"], color=colors, linewidth=2, alpha=0.55)
    ax.scatter(sel["premium_pct"], y, color=colors, s=42, zorder=3, edgecolor="#fcfcfb", linewidth=1)
    ax.axvline(0, color=MUTED, linewidth=0.8)
    ax.set_yticks(y, [f"{s}  (n={n})" for s, n in zip(sel.index, sel["n_salaried"])])
    ax.set_xlabel("Adjusted salary premium vs. an otherwise identical posting (95% bootstrap CI)")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:+.0f}%")
    ax.set_title("Which skills pay more, holding role, seniority, city and company size constant")
    ax.grid(axis="y", visible=False)
    return _save(fig, "02_skill_premiums.png", outdir)


def fig_raw_vs_adjusted(demand: pd.DataFrame, prem: pd.DataFrame, outdir: Path) -> Path:
    j = prem.join(demand[["raw_premium_pct", "postings"]], how="inner").dropna()
    fig, ax = plt.subplots(figsize=(7.5, 6))
    ax.axhline(0, color=MUTED, lw=0.8); ax.axvline(0, color=MUTED, lw=0.8)
    ax.scatter(j["raw_premium_pct"], j["premium_pct"], s=np.sqrt(j["postings"]) * 1.6, color=BLUE, alpha=0.6, edgecolor="#fcfcfb", lw=0.8)
    for s, r in j.iterrows():
        if abs(r["premium_pct"]) > 5.5 or r["raw_premium_pct"] < -30 or r["premium_pct"] < -4:
            ax.annotate(s, (r["raw_premium_pct"], r["premium_pct"]), fontsize=8, xytext=(4, 3), textcoords="offset points", color=TEXT)
    ax.set_xlabel("Raw premium: median salary with skill vs. without")
    ax.set_ylabel("Adjusted premium (regression)")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:+.0f}%"); ax.yaxis.set_major_formatter(lambda v, _: f"{v:+.0f}%")
    ax.set_title("Raw vs. adjusted premium: most of the raw gap is role mix, not the skill")
    return _save(fig, "03_raw_vs_adjusted.png", outdir)


def _heatmap(ax, M: pd.DataFrame, norm, cmap, fmt="{:.1f}", fontsize=7.5):
    im = ax.imshow(M.to_numpy(dtype=float), cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(M.shape[1]), M.columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(M.shape[0]), M.index, fontsize=8)
    ax.grid(False)
    for (i, j), v in np.ndenumerate(M.to_numpy(dtype=float)):
        if np.isfinite(v):
            ax.text(j, i, fmt.format(v), ha="center", va="center", fontsize=fontsize,
                    color="#ffffff" if (norm(v) < 0.22 or norm(v) > 0.78) else TEXT)
    return im


def fig_cooccurrence(L: pd.DataFrame, outdir: Path) -> Path:
    arr = np.log2(L.clip(lower=0.25, upper=4).to_numpy(dtype=float).copy())
    np.fill_diagonal(arr, np.nan)
    M = pd.DataFrame(arr, index=L.index, columns=L.columns)
    fig, ax = plt.subplots(figsize=(0.42 * len(L) + 2, 0.42 * len(L) + 1.5))
    im = _heatmap(ax, M, TwoSlopeNorm(vmin=-2, vcenter=0, vmax=2), DIV, fmt="", fontsize=6)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02, ticks=[-2, -1, 0, 1, 2])
    cb.set_ticklabels(["0.25x", "0.5x", "1x", "2x", "4x"]); cb.set_label("Lift: how much more often two skills appear together than chance")
    ax.set_title("Skill co-occurrence (lift) among the most common skills")
    return _save(fig, "04_cooccurrence_lift.png", outdir)


def fig_index_heatmap(index: pd.DataFrame, n: pd.Series, outdir: Path, name: str, title: str, skills: list[str]) -> Path:
    M = index.loc[[s for s in skills if s in index.index]]
    M.columns = [f"{c}\n(n={n[c]})" for c in M.columns]
    fig, ax = plt.subplots(figsize=(0.75 * M.shape[1] + 2.5, 0.3 * M.shape[0] + 1.5))
    im = _heatmap(ax, M, TwoSlopeNorm(vmin=0.4, vcenter=1.0, vmax=1.8), DIV, fmt="{:.2f}")
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label("Demand index (1.0 = same share as the whole market)")
    ax.set_title(title)
    return _save(fig, name, outdir)


def fig_trends(trend: pd.DataFrame, outdir: Path, n_up: int = 4, n_down: int = 3) -> Path | None:
    if trend.empty:
        return None
    monthly: pd.DataFrame = trend.attrs["monthly"]
    sig = trend[trend["p_value"] < 0.1]
    pick = list(sig.head(n_up).index) + list(sig.tail(n_down).index)
    pick = list(dict.fromkeys(pick))[:8]
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(monthly.shape[1])
    for i, s in enumerate(pick):
        y = monthly.loc[s].to_numpy() * 100
        ax.plot(x, y, color=SERIES[i], lw=2, label=s)
        ax.text(x[-1] + 0.15, y[-1], s, color=SERIES[i], fontsize=8.5, va="center")
    ax.set_xticks(x, monthly.columns, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Share of postings mentioning the skill")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.set_xlim(0, len(x) - 1 + 2.2)
    ax.set_title("Demand shifts: fastest rising and falling skills by month")
    ax.legend(loc="upper left", ncol=2, fontsize=8)
    return _save(fig, "07_demand_trends.png", outdir)


def fig_salary_by(sal: pd.DataFrame, outdir: Path, name: str, title: str) -> Path:
    s = sal.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 0.4 * len(s) + 1.2))
    y = np.arange(len(s))
    ax.hlines(y, s["p25"] / 1000, s["p75"] / 1000, color=BLUE, lw=6, alpha=0.35)
    ax.scatter(s["median"] / 1000, y, color=BLUE, s=48, zorder=3, edgecolor="#fcfcfb", lw=1)
    for i, (m, n) in enumerate(zip(s["median"], s["n"])):
        ax.text(s["p75"].iloc[i] / 1000 + 3, i, f"median ${m/1000:.0f}k  (n={n})", va="center", fontsize=8, color=MUTED)
    ax.set_yticks(y, s.index)
    ax.set_xlabel("Annual salary midpoint, USD thousands (bar = 25th-75th percentile, dot = median)")
    ax.set_title(title)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(left=0)
    return _save(fig, name, outdir)


# ----------------------------------------------------------------------------
def _md_table(df: pd.DataFrame, cols: list[str] | None = None, index: bool = True, floatfmt="{:.2f}") -> str:
    d = df if cols is None else df[cols]
    d = d.copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else floatfmt.format(v))
    if index:
        d = d.reset_index()
    header = "| " + " | ".join(str(c) for c in d.columns) + " |"
    sep = "|" + "|".join("---" for _ in d.columns) + "|"
    rows = ["| " + " | ".join(str(v) for v in r) + " |" for r in d.itertuples(index=False)]
    return "\n".join([header, sep, *rows])


def write_report(ctx: dict, outdir: Path) -> Path:
    df, demand, prem, combos, triples = ctx["df"], ctx["demand"], ctx["prem"], ctx["combos"], ctx["triples"]
    city, size, trend = ctx["city"], ctx["size"], ctx["trend"]
    synthetic = (df["source"] == "synthetic").any()
    n_sal = int(df["has_salary"].sum())
    L = []
    L.append("# Job Market Decoder: report\n")
    if synthetic:
        L.append("> **Demo data.** This report was generated from the synthetic corpus (`jmd synth`), not from live "
                 "postings. The numbers illustrate what the pipeline produces; re-run `jmd scrape` + `jmd build` + "
                 "`jmd analyze` with network access to get real market figures.\n")
    L.append("## 1. Dataset\n")
    L.append(_md_table(pd.DataFrame({
        "value": [len(df), n_sal, f"{n_sal/len(df):.0%}", df["company"].nunique(), ", ".join(sorted(df["source"].unique())),
                  f"{df['posted_at'].min().date()} to {df['posted_at'].max().date()}" if df["posted_at"].notna().any() else "n/a"]},
        index=["postings (data roles, deduplicated)", "postings with a usable annual salary", "salary coverage", "distinct companies",
               "sources", "posting dates"]), index=True))
    L.append("\n**Postings by role family**\n")
    L.append(_md_table(df["role"].value_counts().rename("postings").to_frame()))
    L.append("\n**Salary by role** (USD, annual midpoint)\n")
    L.append(_md_table(ctx["sal_role"], floatfmt="{:,.0f}"))
    L.append("\n**Salary by city**\n")
    L.append(_md_table(ctx["sal_city"], floatfmt="{:,.0f}"))
    L.append("\n**Salary by company size**\n")
    L.append(_md_table(ctx["sal_size"], floatfmt="{:,.0f}"))

    L.append("\n## 2. Which skills are in demand\n")
    L.append("![top skills](figures/01_top_skills.png)\n")
    L.append(_md_table(demand.head(30)[["postings", "share", "n_salaried", "median_with", "raw_premium_pct"]].assign(
        share=lambda d: d["share"] * 100).rename(columns={"share": "share_%", "median_with": "median_salary_usd", "raw_premium_pct": "raw_premium_%"}),
        floatfmt="{:,.1f}"))
    L.append("\n**Skill share by role family** (top 20 skills, % of postings)\n")
    L.append(_md_table((ctx["by_role"].loc[demand.head(20).index] * 100), floatfmt="{:.0f}"))

    L.append("\n## 3. Which skills pay more\n")
    L.append("The raw gap (median salary of postings with vs. without a skill) mostly reflects *who* asks for the skill: "
             "ML engineers both earn more and ask for PyTorch. The adjusted premium comes from a ridge regression of "
             "log(salary) on skill indicators plus role, seniority, city, company size, remote flag and source, so it "
             "compares postings that are otherwise alike. Intervals are 95% bootstrap intervals over postings.\n")
    L.append(f"Model: n = {prem.attrs.get('n_obs')} salaried postings, R² = {prem.attrs.get('r2', float('nan')):.2f}.\n")
    L.append("![premiums](figures/02_skill_premiums.png)\n")
    L.append("![raw vs adjusted](figures/03_raw_vs_adjusted.png)\n")
    L.append("**Top adjusted premiums**\n")
    L.append(_md_table(prem.head(20)[["premium_pct", "ci_lo_pct", "ci_hi_pct", "n_salaried", "significant"]], floatfmt="{:+.1f}"))
    L.append("\n**Skills associated with lower pay (after adjustment)**\n")
    L.append(_md_table(prem.tail(10).iloc[::-1][["premium_pct", "ci_lo_pct", "ci_hi_pct", "n_salaried", "significant"]], floatfmt="{:+.1f}"))

    L.append("\n## 4. Skill combinations\n")
    L.append("![cooccurrence](figures/04_cooccurrence_lift.png)\n")
    L.append("**Most common 3-skill bundles**\n")
    L.append(_md_table(triples.assign(share=lambda d: d["share"] * 100).rename(columns={"share": "share_%"}), index=False, floatfmt="{:.1f}"))
    L.append("\n**Rare but valuable combinations** (pairs in ≤3% of postings; premium vs. the better-paid single skill)\n")
    if combos.empty:
        L.append("_Not enough salaried postings to evaluate rare pairs._")
    else:
        L.append("Premiums here are on salary residuals after role, seniority, city, company size and remote, so a pair "
                 "does not score just for being typical of a well-paid role. `vs_similar` = vs. otherwise similar postings; "
                 "`vs_either` = vs. the better-paid of the two skills on its own; `t` = t-statistic of the residual mean.\n")
        sig = combos[combos["t_stat"] >= 2.0] if "t_stat" in combos else combos
        L.append(_md_table(sig.head(20).assign(share=lambda d: d["share"] * 100)[
            ["a", "b", "postings", "share", "lift", "n_salaried", "median_both", "premium_vs_similar_pct", "premium_vs_either_pct", "t_stat"]]
            .rename(columns={"share": "share_%", "premium_vs_similar_pct": "vs_similar_%", "premium_vs_either_pct": "vs_either_%", "t_stat": "t"}),
            index=False, floatfmt="{:,.1f}"))

    L.append("\n## 5. Demand by city and company size\n")
    L.append("Index = skill share in the segment / skill share overall. 1.3 means the skill is asked for 30% more often than in the market as a whole.\n")
    L.append("![city](figures/05_city_demand_index.png)\n")
    L.append("**Where each skill is over-represented** (cities with the highest index, among skills with ≥100 postings)\n")
    hot = []
    for s in demand[demand["postings"] >= 100].index:
        if s in city["index"].index:
            row = city["index"].loc[s].dropna().sort_values(ascending=False)
            if len(row):
                hot.append({"skill": s, "top_city": row.index[0], "index": row.iloc[0], "lowest_city": row.index[-1], "index_low": row.iloc[-1]})
    L.append(_md_table(pd.DataFrame(hot).sort_values("index", ascending=False).head(25), index=False))
    L.append("\n![size](figures/06_company_size_demand_index.png)\n")
    L.append("**Company size: skills that tilt small vs. large** (index in smallest vs. largest bucket)\n")
    si = size["index"]
    if si.shape[1] >= 2:
        tilt = pd.DataFrame({"small (" + si.columns[0] + ")": si.iloc[:, 0], "large (" + si.columns[-1] + ")": si.iloc[:, -1]})
        tilt["ratio_large_vs_small"] = tilt.iloc[:, 1] / tilt.iloc[:, 0]
        tilt = tilt.loc[demand[demand["postings"] >= 100].index.intersection(tilt.index)].dropna()
        L.append("_Most large-company:_\n\n" + _md_table(tilt.sort_values("ratio_large_vs_small", ascending=False).head(10)))
        L.append("\n_Most small-company:_\n\n" + _md_table(tilt.sort_values("ratio_large_vs_small").head(10)))

    L.append("\n## 6. Demand over time\n")
    if trend.empty:
        L.append("_Not enough dated postings to estimate trends._")
    else:
        L.append("![trends](figures/07_demand_trends.png)\n")
        t = trend.assign(share_first=lambda d: d["share_first"] * 100, share_last=lambda d: d["share_last"] * 100)
        L.append("**Rising**\n\n" + _md_table(t.head(12)[["share_first", "share_last", "growth_ratio", "slope_pp_per_month", "p_value", "postings"]], floatfmt="{:.2f}"))
        L.append("\n**Falling**\n\n" + _md_table(t.tail(8).iloc[::-1][["share_first", "share_last", "growth_ratio", "slope_pp_per_month", "p_value", "postings"]], floatfmt="{:.2f}"))

    L.append("\n## 7. What should I learn next?\n")
    L.append("Example runs of the recommendation engine (`jmd recommend --have ... --role ...`). Scores blend demand in the "
             "target segment, adjusted pay premium, adjacency to skills already held, and the share of postings newly unlocked.\n")
    for title, table in ctx["examples"]:
        L.append(f"**{title}**\n\n" + _md_table(table, index=False) + "\n")

    L.append("\n## Method notes\n")
    L.append("- Skills are extracted with a curated regex taxonomy (`data/taxonomy/skills.yaml`, "
             f"{ctx['n_skills']} skills). Case-sensitive patterns guard short names (R, SAS, Go). `jmd discover` lists "
             "frequent terms not yet in the taxonomy.\n"
             "- Salaries come from structured fields when a source publishes them, otherwise from a regex over the description "
             "(ranges like `$120k-$150k`, `€55,000 to €70,000 per year`, hourly/monthly rates are annualised, non-USD converted at fixed rates).\n"
             "- Company size is taken from the source when available, else from a lookup table of known companies, else from "
             "text cues (`Series B`, `Fortune 500`, `2,000+ employees`).\n"
             "- Rare combos are scored on salary residuals (log salary minus what role, seniority, city, size, remote and source predict), "
             "compared with the better-paid of the two skills on its own.\n"
             "- Postings are deduplicated on company + title + opening of the description, so a role cross-posted on several boards counts once.\n")
    path = outdir / "report.md"
    path.write_text("\n".join(L), encoding="utf-8")
    return path
