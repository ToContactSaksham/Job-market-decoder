import pandas as pd
import pytest

from jmd.clean import annualise_usd, canonical_city, clean, infer_company_size, parse_salary_text, role_family, seniority, _load_cities
from jmd.schema import COLUMNS
from jmd.synth import generate


@pytest.mark.parametrize("text,expected", [
    ("The base salary range for this role is $120,000-$150,000 per year.", (120000, 150000, "USD", "year")),
    ("Salary: $95k - $120k USD", (95000, 120000, "USD", "year")),
    ("Base pay: $110K–$140K", (110000, 140000, "USD", "year")),
    ("Compensation €55,000 to €70,000 annually", (55000, 70000, "EUR", "year")),
    ("£45k-£60k", (45000, 60000, "GBP", "year")),
    ("Compensation: $4,000 to $6,000 per month", (4000, 6000, "USD", "month")),
    ("We pay 60-80 EUR per hour", (60, 80, "EUR", "hour")),
    ("This role pays $85/hour", (85, 85, "USD", "hour")),
    ("salary range 120k-150k", (120000, 150000, "USD", "year")),
])
def test_parse_salary_text_positive(text, expected):
    assert parse_salary_text(text) == expected


@pytest.mark.parametrize("text", [
    "3-5 years of experience with Python", "10-15 years", "between 2015 and 2020 we grew", "team of 10-20 people", "Requirements: 5-10 years",
    "", "Founded in 2012, Series B in 2019",
])
def test_parse_salary_text_negative(text):
    assert parse_salary_text(text) == (None, None, None, None)


def test_annualise_usd_converts_and_filters():
    assert annualise_usd(4000, 6000, "USD", "month") == (48000, 72000)
    lo, hi = annualise_usd(45000, 60000, "GBP", "year")
    assert 55000 < lo < 60000 and 74000 < hi < 78000
    assert annualise_usd(5000, 8000, "USD", "year") == (None, None)      # below floor
    assert annualise_usd(1_000_000, 2_000_000, "USD", "year") == (None, None)  # above ceiling
    assert annualise_usd(None, None, None, None) == (None, None)


def test_role_and_seniority():
    assert role_family("Senior Analytics Engineer") == "Analytics Engineer"
    assert role_family("Machine Learning Engineer, Ranking") == "ML Engineer"
    assert role_family("Head of Data") == "Data Manager"
    assert role_family("Software Engineer") == "Other"
    assert seniority("Senior Data Scientist") == "Senior"
    assert seniority("Data Analyst I") == "Junior"
    assert seniority("Staff Data Engineer") == "Staff"
    assert seniority("Data Scientist") == "Mid"
    assert seniority("Data Science Manager") == "Manager"


def test_canonical_city():
    cities = _load_cities()
    assert canonical_city("San Francisco, CA", cities) == ("San Francisco Bay Area", "US")
    assert canonical_city("Remote - US", cities)[0] == "Remote"
    assert canonical_city("Remote - US", cities)[1] == "US"
    assert canonical_city("London, United Kingdom", cities) == ("London", "UK")
    assert canonical_city("Timbuktu", cities)[0] == "Other"


def test_infer_company_size_from_text_and_lookup():
    sizes = {"stripe": "5000+"}
    assert infer_company_size(pd.Series({"company": "Stripe, Inc.", "description": ""}), sizes) == "5000+"
    assert infer_company_size(pd.Series({"company": "STRIPE", "description": ""}), sizes) == "5000+"
    assert infer_company_size(pd.Series({"company": "X", "description": "We are a Series B startup."}), sizes) == "51-200"
    assert infer_company_size(pd.Series({"company": "X", "description": "A Fortune 500 company with 20,000 employees"}), sizes) == "5000+"
    assert infer_company_size(pd.Series({"company": "X", "description": "nothing here", "company_size": "201-1000"}), sizes) == "201-1000"
    assert infer_company_size(pd.Series({"company": "X", "description": "nothing here"}), sizes) == "Unknown"


def test_clean_end_to_end_on_synthetic():
    raw = pd.DataFrame([p.to_row() for p in generate(300, seed=1)], columns=COLUMNS)
    df = clean(raw)
    assert len(df) == 300
    assert set(df["role"]) <= {"Data Analyst", "Data Scientist", "Data Engineer", "ML Engineer", "Analytics Engineer", "BI Developer", "Data Manager"}
    assert 0.4 < df["has_salary"].mean() < 0.7
    assert df["salary_mid_usd"].dropna().between(25_000, 600_000).all()
    assert (df["salary_source"] == "parsed_text").sum() > 0 and (df["salary_source"] == "structured").sum() > 0
    assert "Remote" in set(df["city"]) and "New York" in set(df["city"])
    assert df["company_size"].astype(str).isin(["1-50", "51-200", "201-1000", "1001-5000", "5000+", "Unknown"]).all()


def test_clean_dedupes_cross_posted_jobs():
    raw = pd.DataFrame([p.to_row() for p in generate(5, seed=2)], columns=COLUMNS)
    dup = raw.copy(); dup["id"] = dup["id"] + ":copy"; dup["source"] = "other"
    df = clean(pd.concat([raw, dup], ignore_index=True))
    assert len(df) == 5
