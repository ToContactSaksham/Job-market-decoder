"""The synthetic market has known parameters; the analysis must recover them."""
import numpy as np
import pandas as pd
import pytest

from jmd import analysis as A
from jmd.clean import clean
from jmd.recommend import Recommender, to_frame
from jmd.schema import COLUMNS
from jmd.skills import SkillExtractor
from jmd.synth import PREMIUM, generate


@pytest.fixture(scope="module")
def market():
    raw = pd.DataFrame([p.to_row() for p in generate(2500, seed=7)], columns=COLUMNS)
    df = clean(raw)
    ex = SkillExtractor()
    X = ex.matrix(df["text"])
    return df, X, ex


def test_demand_basic(market):
    df, X, _ = market
    d = A.skill_demand(X, df)
    assert d.index[0] in {"SQL", "Python"} and d["share"].between(0, 1).all()
    assert d.loc["SQL", "postings"] > d.loc["Kafka", "postings"]


def test_adjusted_premiums_recover_generative_truth(market):
    df, X, _ = market
    prem = A.adjusted_premiums(X, df, n_boot=30)
    # Encoded premiums: LLMs +12%, Causal Inference +10%, Excel -7%, Power BI -5%.
    assert prem.loc["LLMs", "premium_pct"] > 7
    assert prem.loc["Causal Inference", "premium_pct"] > 5
    assert prem.loc["Excel", "premium_pct"] < -3
    assert prem.loc["Power BI", "premium_pct"] < -1
    # Ranking: true premium should correlate with the estimate across skills with support.
    truth = pd.Series({s: (PREMIUM.get(s, 1.0) - 1) * 100 for s in prem.index})
    assert np.corrcoef(truth, prem["premium_pct"])[0, 1] > 0.75
    assert (prem["ci_lo_pct"] <= prem["premium_pct"]).all() and (prem["premium_pct"] <= prem["ci_hi_pct"]).all()
    assert prem.attrs["r2"] > 0.8


def test_cooccurrence_finds_encoded_pairs(market):
    _, X, _ = market
    co = A.cooccurrence(X, min_pair=5).set_index(["a", "b"])
    def lift(a, b):
        return co.loc[(a, b), "lift"] if (a, b) in co.index else co.loc[(b, a), "lift"]
    assert lift("Spark", "Scala") > 1.5 and lift("dbt", "Snowflake") > 1.3 and lift("Kubernetes", "Docker") > 1.5
    assert lift("Excel", "PyTorch") < 1.0


def test_city_and_size_indices(market):
    df, X, _ = market
    city = A.demand_by_city(X, df, min_n=30)
    assert city["index"].loc["Excel", "San Francisco Bay Area"] < 0.85
    assert city["index"].loc["AWS", "Seattle"] > 1.2
    size = A.demand_by_company_size(X, df, min_n=30)
    assert size["index"].loc["dbt", "5000+"] < size["index"].loc["dbt", "1-50"]
    assert list(size["share"].columns) == ["1-50", "51-200", "201-1000", "1001-5000", "5000+"]


def test_trend_detects_llm_growth(market):
    df, X, _ = market
    t = A.demand_trend(X, df, min_month_n=20)
    assert t.loc["LLMs", "growth_ratio"] > 1.3 and t.loc["LLMs", "slope_pp_per_month"] > 0
    assert t.loc["Hadoop", "growth_ratio"] < 1.0


def test_rare_combos_and_triples(market):
    df, X, _ = market
    combos = A.rare_valuable_combos(X, df, min_pair=8, min_salaried=5)
    assert {"a", "b", "premium_vs_either_pct", "t_stat"} <= set(combos.columns)
    assert (combos["share"] <= 0.03).all()
    tri = A.frequent_triples(X, min_support=0.05)
    assert len(tri) > 0 and tri["postings"].is_monotonic_decreasing


def test_recommender(market):
    df, X, ex = market
    rec = Recommender(X, df, ex.category, premiums=A.adjusted_premiums(X, df, n_boot=5))
    out = rec.recommend(["python", "SQL"], role="Data Engineer", top=5)
    names = [r.skill for r in out]
    assert len(names) == 5 and "Python" not in names and "SQL" not in names
    assert "Spark" in names or "ETL" in names or "Airflow" in names
    assert all(r.reasons for r in out)
    assert "Communication" not in names  # soft skills excluded by default
    frame = to_frame(out)
    assert list(frame.columns)[:3] == ["skill", "category", "score"]
    cov = rec.coverage(["Python", "SQL", "Spark", "Airflow", "AWS", "ETL", "Data Warehousing"], role="Data Engineer")
    assert cov["qualified_share"] > 0 and cov["have"] == ["Python", "SQL", "Spark", "Airflow", "AWS", "ETL", "Data Warehousing"]
    path = rec.learning_path(["SQL"], role="Data Analyst", steps=3)
    assert len(path) == 3 and len({r.skill for r in path}) == 3
