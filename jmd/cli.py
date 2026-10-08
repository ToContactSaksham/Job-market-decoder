"""Command-line interface: scrape | synth | build | analyze | recommend | discover | all."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from . import analysis as A
from . import config
from .clean import clean
from .recommend import Recommender, to_frame
from .report import (fig_cooccurrence, fig_index_heatmap, fig_premiums, fig_raw_vs_adjusted, fig_salary_by, fig_top_skills,
                     fig_trends, write_report)
from .schema import COLUMNS
from .skills import SkillExtractor, discover_candidates

log = logging.getLogger("jmd")


# ----------------------------------------------------------------------------
def cmd_scrape(args):
    from .scrapers import SCRAPERS
    outdir = config.RAW_DIR / "live"
    outdir.mkdir(parents=True, exist_ok=True)
    names = args.sources.split(",") if args.sources else list(SCRAPERS)
    total = 0
    for name in names:
        mod = SCRAPERS[name]
        try:
            posts = mod.fetch(limit=args.limit, query=args.query)
        except Exception as exc:
            log.error("%s failed: %s", name, exc)
            continue
        path = outdir / f"{name}_{date.today().isoformat()}.csv"
        pd.DataFrame([p.to_row() for p in posts], columns=COLUMNS).to_csv(path, index=False)
        log.info("%s: %d postings -> %s", name, len(posts), path)
        total += len(posts)
    print(f"scraped {total} postings into {outdir}")


def cmd_synth(args):
    from .synth import generate
    outdir = config.RAW_DIR / "demo"
    outdir.mkdir(parents=True, exist_ok=True)
    posts = generate(n=args.n, seed=args.seed)
    path = outdir / "synthetic.csv"
    pd.DataFrame([p.to_row() for p in posts], columns=COLUMNS).to_csv(path, index=False)
    print(f"generated {len(posts)} synthetic postings -> {path}")


def _load_raw(source_dir: str) -> pd.DataFrame:
    paths = sorted((config.RAW_DIR / source_dir).glob("*.csv"))
    if not paths:
        sys.exit(f"no raw CSVs in {config.RAW_DIR / source_dir}; run `jmd scrape` or `jmd synth` first")
    frames = [pd.read_csv(p, dtype={"tags": str}) for p in paths]
    raw = pd.concat(frames, ignore_index=True)
    log.info("loaded %d raw postings from %d files", len(raw), len(paths))
    return raw


def cmd_build(args):
    raw = _load_raw(args.raw)
    df = clean(raw)
    ex = SkillExtractor()
    X = ex.matrix(df["text"])
    df.drop(columns=["text"]).to_csv(config.PROCESSED_DIR / "postings.csv", index=False)
    X.astype(int).to_csv(config.PROCESSED_DIR / "skills_matrix.csv", index=False)
    print(f"built {len(df)} clean postings ({df['has_salary'].sum()} with salary) x {X.shape[1]} skills -> {config.PROCESSED_DIR}")


def _load_processed():
    try:
        df = pd.read_csv(config.PROCESSED_DIR / "postings.csv", parse_dates=["posted_at"])
        X = pd.read_csv(config.PROCESSED_DIR / "skills_matrix.csv").astype(bool)
    except FileNotFoundError:
        sys.exit("processed data not found; run `jmd build` first")
    df["company_size"] = pd.Categorical(df["company_size"].astype(str), categories=config.COMPANY_SIZE_BUCKETS + ["Unknown"], ordered=True)
    df["month"] = df["month"].astype(object).where(df["month"].notna(), None)
    return df, X


def cmd_analyze(args):
    df, X = _load_processed()
    ex = SkillExtractor()
    figdir = config.FIGURE_DIR
    log.info("demand"); demand = A.skill_demand(X, df)
    log.info("premiums (bootstrap %d)", args.boot); prem = A.adjusted_premiums(X, df, n_boot=args.boot)
    log.info("combinations"); combos = A.rare_valuable_combos(X, df); triples = A.frequent_triples(X)
    log.info("segments"); city = A.demand_by_city(X, df); size = A.demand_by_company_size(X, df); trend = A.demand_trend(X, df)
    top = list(demand.head(25).index)
    L = A.lift_matrix(X, top)

    fig_top_skills(demand, figdir)
    fig_premiums(prem, figdir)
    fig_raw_vs_adjusted(demand, prem, figdir)
    fig_cooccurrence(L, figdir)
    hm_skills = [s for s in demand.index if demand.loc[s, "postings"] >= 100][:30]
    fig_index_heatmap(city["index"], city["n"], figdir, "05_city_demand_index.png", "Skill demand by city (index vs. whole market)", hm_skills)
    fig_index_heatmap(size["index"], size["n"], figdir, "06_company_size_demand_index.png", "Skill demand by company size (index vs. whole market)", hm_skills)
    fig_trends(trend, figdir)
    sal_role, sal_city, sal_size = A.salary_by(df, "role"), A.salary_by(df, "city"), A.salary_by(df, "company_size")
    fig_salary_by(sal_role, figdir, "08_salary_by_role.png", "Salary by role family")
    fig_salary_by(sal_city, figdir, "09_salary_by_city.png", "Salary by city")

    # tables
    tdir = config.OUTPUT_DIR / "tables"; tdir.mkdir(exist_ok=True)
    demand.to_csv(tdir / "skill_demand.csv"); prem.to_csv(tdir / "skill_premiums.csv"); combos.to_csv(tdir / "rare_combos.csv", index=False)
    triples.to_csv(tdir / "frequent_triples.csv", index=False); city["index"].to_csv(tdir / "city_demand_index.csv")
    size["index"].to_csv(tdir / "company_size_demand_index.csv"); A.cooccurrence(X).to_csv(tdir / "cooccurrence.csv", index=False)
    if not trend.empty:
        trend.to_csv(tdir / "demand_trend.csv"); trend.attrs["monthly"].to_csv(tdir / "monthly_share.csv")

    rec = Recommender(X, df, ex.category, premiums=prem)
    examples = [
        ("Analyst with SQL + Excel + Tableau, targeting Data Analyst roles", to_frame(rec.recommend(["SQL", "Excel", "Tableau"], role="Data Analyst", top=8))),
        ("Python + SQL + pandas, targeting Data Scientist roles", to_frame(rec.recommend(["Python", "SQL", "pandas", "Statistics"], role="Data Scientist", top=8))),
        ("Python + SQL + Airflow, targeting Data Engineer roles", to_frame(rec.recommend(["Python", "SQL", "Airflow", "AWS"], role="Data Engineer", top=8))),
    ]
    write_report({"df": df, "demand": demand, "prem": prem, "combos": combos, "triples": triples, "city": city, "size": size, "trend": trend,
                  "sal_role": sal_role, "sal_city": sal_city, "sal_size": sal_size, "by_role": A.demand_by_role(X, df),
                  "examples": examples, "n_skills": X.shape[1]}, config.OUTPUT_DIR)
    print(f"report -> {config.OUTPUT_DIR / 'report.md'}; figures -> {figdir}; tables -> {tdir}")


def cmd_recommend(args):
    df, X = _load_processed()
    ex = SkillExtractor()
    prem_path = config.OUTPUT_DIR / "tables" / "skill_premiums.csv"
    prem = pd.read_csv(prem_path, index_col=0) if prem_path.exists() else None
    rec = Recommender(X, df, ex.category, premiums=prem)
    have = [h for h in args.have.split(",") if h.strip()] if args.have else []
    cov = rec.coverage(have, args.role, args.city)
    seg = " / ".join(x for x in (args.role, args.city) if x) or "all data roles"
    print(f"Target: {seg} ({cov['postings']} postings). You have: {', '.join(cov['have']) or 'nothing yet'}.")
    print(f"You already cover >=60% of the hard skills listed in {cov['qualified_share']:.1%} of postings (mean coverage {cov['mean_coverage']:.0%}).\n")
    recs = rec.recommend(have, args.role, args.city, top=args.top)
    print("Learn next (ranked):")
    for i, r in enumerate(recs, 1):
        print(f"{i:2d}. {r.skill:<24} score {r.score:.2f}  |  " + "; ".join(r.reasons))
    if args.path:
        print("\nSuggested learning path (greedy, each step re-scored):")
        for i, r in enumerate(rec.learning_path(have, args.role, args.city, steps=args.path), 1):
            print(f"  step {i}: {r.skill}  ({r.reasons[0]})")


def cmd_discover(args):
    df, _ = _load_processed()
    ex = SkillExtractor()
    text = df["title"].fillna("") + "\n" + df["description"].fillna("")
    cands = discover_candidates(text, ex, top=args.top)
    print(cands.to_string(index=False))


def cmd_all(args):
    if args.demo:
        cmd_synth(args)
        args.raw = "demo"
    cmd_build(args)
    cmd_analyze(args)


# ----------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(prog="jmd", description="Job Market Decoder")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scrape", help="fetch live postings from public job APIs into data/raw/live/")
    s.add_argument("--sources", help="comma-separated subset of: remoteok,arbeitnow,remotive,jobicy,greenhouse,lever,hn_hiring")
    s.add_argument("--limit", type=int, default=5000); s.add_argument("--query", help="source-specific filter (e.g. greenhouse board list)")
    s.set_defaults(fn=cmd_scrape)

    s = sub.add_parser("synth", help="generate the synthetic demo corpus into data/raw/demo/")
    s.add_argument("--n", type=int, default=4000); s.add_argument("--seed", type=int, default=42)
    s.set_defaults(fn=cmd_synth)

    s = sub.add_parser("build", help="clean raw postings and extract skills into data/processed/")
    s.add_argument("--raw", default="live", help="subfolder of data/raw to read (live | demo)")
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("analyze", help="run all analyses; write outputs/report.md, figures and tables")
    s.add_argument("--boot", type=int, default=200, help="bootstrap resamples for premium CIs")
    s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("recommend", help="what should I learn next?")
    s.add_argument("--have", default="", help="comma-separated skills you already have")
    s.add_argument("--role", help="target role family, e.g. 'Data Scientist'"); s.add_argument("--city", help="target city, e.g. 'New York'")
    s.add_argument("--top", type=int, default=10); s.add_argument("--path", type=int, default=0, help="also print an N-step learning path")
    s.set_defaults(fn=cmd_recommend)

    s = sub.add_parser("discover", help="frequent terms in postings that are not in the taxonomy yet")
    s.add_argument("--top", type=int, default=60)
    s.set_defaults(fn=cmd_discover)

    s = sub.add_parser("all", help="build + analyze (with --demo: synth first)")
    s.add_argument("--demo", action="store_true"); s.add_argument("--raw", default="live"); s.add_argument("--n", type=int, default=4000)
    s.add_argument("--seed", type=int, default=42); s.add_argument("--boot", type=int, default=200)
    s.set_defaults(fn=cmd_all)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args.fn(args)


if __name__ == "__main__":
    main()
