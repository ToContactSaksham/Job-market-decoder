"""Paths and tunables."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = ROOT / "outputs"
FIGURE_DIR = OUTPUT_DIR / "figures"
TAXONOMY_PATH = DATA_DIR / "taxonomy" / "skills.yaml"
COMPANY_SIZE_PATH = DATA_DIR / "taxonomy" / "company_sizes.csv"
CITIES_PATH = DATA_DIR / "taxonomy" / "cities.csv"

# Only annual salaries inside this USD window are used for pay analysis.
SALARY_MIN_USD = 25_000
SALARY_MAX_USD = 600_000

# Approximate FX rates to USD, used only to normalise the minority of
# non-USD postings. Refresh when re-scraping.
FX_TO_USD = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CAD": 0.73, "AUD": 0.65,
    "INR": 0.012, "CHF": 1.12, "SGD": 0.74, "JPY": 0.0067, "BRL": 0.18,
    "PLN": 0.25, "SEK": 0.095, "DKK": 0.145, "NOK": 0.093, "NZD": 0.60,
}

# Working-time assumptions for annualising non-annual salaries.
HOURS_PER_YEAR = 2080
DAYS_PER_YEAR = 260
MONTHS_PER_YEAR = 12

# Minimum number of salaried postings a skill needs before we report a premium.
MIN_SUPPORT_FOR_PREMIUM = 30

COMPANY_SIZE_BUCKETS = ["1-50", "51-200", "201-1000", "1001-5000", "5000+"]

for _d in (RAW_DIR, PROCESSED_DIR, FIGURE_DIR):
    _d.mkdir(parents=True, exist_ok=True)
