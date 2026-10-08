"""Normalise raw postings into an analysis-ready table.

Adds: role family, seniority, canonical city/country, remote flag, company-size
bucket (published, looked up, or inferred from text), annual USD salary
(published fields or parsed from the description), and removes duplicates.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import config
from .schema import DATA_ROLE_PATTERNS

# ----------------------------------------------------------------------------
# Salary parsing
# ----------------------------------------------------------------------------
_CUR_ALT = r"\$|US\$|USD|€|EUR|£|GBP|CAD|C\$|AUD|A\$|INR|₹|CHF|SGD"
_CUR = rf"(?P<cur>{_CUR_ALT})"
_NUM = r"(?P<{n}>\d{{1,3}}(?:,\d{{3}})+|\d{{2,3}}(?:\.\d)?\s?[kK]|\d{{4,6}}|\d{{2,3}})"
_SEP = r"\s*(?:-|–|—|to|and)\s*"
_PERIOD = r"(?:\s*(?:/|per|a|an)\s*(?P<period>year|yr|annum|annually|month|mo|hour|hr|day))?"
SALARY_RANGE_RE = re.compile(
    rf"{_CUR}?\s?{_NUM.format(n='lo')}{_SEP}(?:{_CUR_ALT})?\s?{_NUM.format(n='hi')}\s?(?P<cur2>USD|EUR|GBP|CAD|AUD|INR)?{_PERIOD}",
    re.I,
)
SALARY_SINGLE_RE = re.compile(rf"{_CUR}\s?{_NUM.format(n='lo')}\s?(?P<cur2>USD|EUR|GBP)?{_PERIOD}", re.I)
_CUR_MAP = {"$": "USD", "us$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP", "cad": "CAD", "c$": "CAD",
            "aud": "AUD", "a$": "AUD", "inr": "INR", "₹": "INR", "chf": "CHF", "sgd": "SGD"}
_PERIOD_MAP = {"year": "year", "yr": "year", "annum": "year", "annually": "year", "month": "month", "mo": "month",
               "hour": "hour", "hr": "hour", "day": "day"}


def _to_number(s: str) -> float:
    s = s.replace(",", "").strip()
    if s[-1] in "kK":
        return float(s[:-1]) * 1000
    return float(s)


def parse_salary_text(text: str) -> tuple[float | None, float | None, str | None, str | None]:
    """Find the most plausible salary range in free text. Returns (lo, hi, currency, period)."""
    if not text:
        return None, None, None, None
    best = None
    for m in SALARY_RANGE_RE.finditer(text):
        lo, hi = _to_number(m.group("lo")), _to_number(m.group("hi"))
        if hi < lo:
            continue
        cur = _CUR_MAP.get((m.group("cur") or m.group("cur2") or "").lower())
        period = _PERIOD_MAP.get((m.group("period") or "").lower())
        if not cur and not period and not re.search(r"salar|compensation|pay|base", text[max(0, m.start() - 80):m.start()], re.I):
            continue  # bare number range with no money context: skip (could be years, dates)
        lo, hi, period = _infer_period(lo, hi, period)
        if lo is None:
            continue
        cand = (lo, hi, cur or "USD", period)
        if best is None or (cur and not best[2]) or (hi - lo) < (best[1] - best[0]):
            best = cand
    if best:
        return best
    for m in SALARY_SINGLE_RE.finditer(text):
        v = _to_number(m.group("lo"))
        cur = _CUR_MAP.get((m.group("cur") or m.group("cur2") or "").lower())
        period = _PERIOD_MAP.get((m.group("period") or "").lower())
        v, _, period = _infer_period(v, v, period)
        if v is not None and cur:
            return v, v, cur, period
    return None, None, None, None


def _infer_period(lo, hi, period):
    """Guess the pay period from magnitude when it is not stated."""
    if period:
        return lo, hi, period
    if 15 <= lo <= 400 and hi <= 500:
        return lo, hi, "hour"
    if 1_000 <= lo < 20_000:
        return lo, hi, "month"
    if 20_000 <= lo <= 1_000_000:
        return lo, hi, "year"
    return None, None, None


def annualise_usd(lo, hi, currency, period) -> tuple[float | None, float | None]:
    if lo is None or hi is None:
        return None, None
    mult = {"year": 1, "month": config.MONTHS_PER_YEAR, "day": config.DAYS_PER_YEAR, "hour": config.HOURS_PER_YEAR}.get(period or "year", 1)
    fx = config.FX_TO_USD.get((currency or "USD").upper())
    if fx is None:
        return None, None
    lo_usd, hi_usd = lo * mult * fx, hi * mult * fx
    if not (config.SALARY_MIN_USD <= lo_usd <= config.SALARY_MAX_USD and hi_usd <= config.SALARY_MAX_USD * 1.5):
        return None, None
    return lo_usd, hi_usd


# ----------------------------------------------------------------------------
# Role, seniority, location, company size
# ----------------------------------------------------------------------------
_ROLE_RES = [(name, re.compile(p, re.I)) for name, p in DATA_ROLE_PATTERNS.items()]
_SENIORITY = [
    ("Intern", re.compile(r"\bintern(?:ship)?\b|\bco-?op\b", re.I)),
    ("Manager", re.compile(r"\bmanager\b|\bhead of\b|\bdirector\b|\bvp\b|\bvice president\b|\bchief\b", re.I)),
    ("Lead", re.compile(r"\blead\b|\bprincipal\b", re.I)),
    ("Staff", re.compile(r"\bstaff\b", re.I)),
    ("Senior", re.compile(r"\bsenior\b|\bsr\.?\b|\biii\b|\biv\b", re.I)),
    ("Junior", re.compile(r"\bjunior\b|\bjr\.?\b|\bentry[\s\-]level\b|\bgraduate\b|\bassociate\b|\bi\b(?!i)", re.I)),
]
_REMOTE_RE = re.compile(r"\bremote\b|\bwork from home\b|\bwfh\b|\banywhere\b|\bdistributed\b", re.I)
_SIZE_TEXT = [
    ("1-50", re.compile(r"\b(?:seed|pre-seed|series a)\b|\bstartup of \d{1,2}\b|\bteam of \d{1,2}\b|\b(?:[1-4]?\d|50) employees\b", re.I)),
    ("51-200", re.compile(r"\bseries b\b|\b(?:5[1-9]|1\d\d|200) employees\b|\b(?:50|100|150)\+ (?:people|employees)\b", re.I)),
    ("201-1000", re.compile(r"\bseries [cd]\b|\b(?:2\d\d|[3-9]\d\d|1,?000) employees\b|\b(?:200|250|300|500)\+ (?:people|employees)\b", re.I)),
    ("1001-5000", re.compile(r"\b(?:[1-4],?\d{3}|5,?000) employees\b|\b(?:1,?000|2,?000|3,?000)\+ (?:people|employees)\b|\bseries [ef]\b", re.I)),
    ("5000+", re.compile(r"\bfortune (?:50|100|500|1000)\b|\b(?:[5-9]|\d{2,3}),?\d{3} employees\b|\b(?:5,?000|10,?000|20,?000|50,?000)\+ (?:people|employees)\b|\bglobal 2000\b|\bs&p 500\b|\bftse 100\b|\bnyse\b|\bnasdaq[\s\-]listed\b|\bpublicly traded\b", re.I)),
]
_SYNTH_SIZE_HINTS = {"seed-stage": "1-50", "Series B": "51-200", "mid-sized": "201-1000", "large company": "1001-5000", "Fortune-500": "5000+"}


def _load_cities() -> list[tuple[re.Pattern, str, str]]:
    df = pd.read_csv(config.CITIES_PATH)
    return [(re.compile(r.pattern, re.I), r.city, r.country) for r in df.itertuples()]


_SUFFIX_RE = re.compile(r"\b(?:inc|llc|ltd|limited|corp|corporation|co|company|gmbh|plc|ag|sa|bv|labs|technologies|technology)\b\.?", re.I)


def _company_key(name: str) -> str:
    name = _SUFFIX_RE.sub("", name)
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _load_company_sizes() -> dict[str, str]:
    df = pd.read_csv(config.COMPANY_SIZE_PATH)
    return {_company_key(str(c)): s for c, s in zip(df.company, df["size"])}


def role_family(title: str) -> str:
    for name, rx in _ROLE_RES:
        if rx.search(title or ""):
            return name
    return "Other"


def seniority(title: str) -> str:
    for name, rx in _SENIORITY:
        if rx.search(title or ""):
            return name
    return "Mid"


def canonical_city(location: str, cities) -> tuple[str, str]:
    loc = location or ""
    for rx, city, country in cities:
        if rx.search(loc):
            return city, country
    if _REMOTE_RE.search(loc) or not loc.strip():
        return "Remote", _country_from_remote(loc)
    return "Other", _country_from_remote(loc)


def _country_from_remote(loc: str) -> str:
    l = loc.lower()
    for key, c in (("usa", "US"), ("united states", "US"), ("us", "US"), ("uk", "UK"), ("united kingdom", "UK"), ("europe", "EU"),
                   ("emea", "EU"), ("germany", "DE"), ("canada", "CA"), ("india", "IN"), ("worldwide", "Global"), ("anywhere", "Global")):
        if re.search(rf"\b{re.escape(key)}\b", l):
            return c
    return "Unknown"


def infer_company_size(row: pd.Series, sizes: dict[str, str]) -> str:
    if isinstance(row.get("company_size"), str) and row["company_size"] in config.COMPANY_SIZE_BUCKETS:
        return row["company_size"]
    key = _company_key(str(row.get("company", "")))
    if key and key in sizes:
        return sizes[key]
    text = str(row.get("description", ""))[:4000]
    for hint, size in _SYNTH_SIZE_HINTS.items():
        if hint in text:
            return size
    for size, rx in _SIZE_TEXT:
        if rx.search(text):
            return size
    return "Unknown"


# ----------------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------------
def clean(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["description"] = df["description"].fillna("").astype(str)
    df["title"] = df["title"].fillna("").astype(str)
    df["company"] = df["company"].fillna("").astype(str).str.strip()

    # Dedupe: same company + title + first 300 chars of description => same posting reposted elsewhere.
    key = (df["company"].str.lower() + "|" + df["title"].str.lower().str.replace(r"\s+", " ", regex=True)
           + "|" + df["description"].str.lower().str[:300])
    df = df.loc[~key.duplicated()].copy()

    df["role"] = df["title"].map(role_family)
    df = df[df["role"] != "Other"].copy()
    df["seniority"] = df["title"].map(seniority)

    cities = _load_cities()
    cc = df["location"].fillna("").map(lambda s: canonical_city(s, cities))
    df["city"] = [c for c, _ in cc]
    df["country"] = [k for _, k in cc]
    df["remote"] = df["remote"].map(lambda v: bool(v) if pd.notna(v) else False) | df["location"].fillna("").str.contains(_REMOTE_RE)
    df.loc[df["remote"] & (df["city"] == "Other"), "city"] = "Remote"

    sizes = _load_company_sizes()
    df["company_size"] = df.apply(lambda r: infer_company_size(r, sizes), axis=1)
    df["company_size"] = pd.Categorical(df["company_size"], categories=config.COMPANY_SIZE_BUCKETS + ["Unknown"], ordered=True)

    # Salary: prefer structured fields, fall back to the description text.
    parsed = pd.DataFrame(df["description"].map(parse_salary_text).tolist(), index=df.index,
                          columns=["p_min", "p_max", "p_cur", "p_period"])
    for c in ("salary_min", "salary_max"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    need = df["salary_min"].isna() & df["salary_max"].isna()
    df["salary_min"] = df["salary_min"].where(~need, pd.to_numeric(parsed["p_min"], errors="coerce"))
    df["salary_max"] = df["salary_max"].where(~need, pd.to_numeric(parsed["p_max"], errors="coerce"))
    df["salary_currency"] = df["salary_currency"].astype(object).where(~need, parsed["p_cur"].astype(object))
    df["salary_period"] = df["salary_period"].astype(object).where(~need, parsed["p_period"].astype(object))
    df["salary_source"] = np.where(df["salary_min"].notna() | df["salary_max"].notna(), np.where(need, "parsed_text", "structured"), "none")
    df["salary_max"] = df["salary_max"].fillna(df["salary_min"])
    df["salary_min"] = df["salary_min"].fillna(df["salary_max"])
    usd = [annualise_usd(None if pd.isna(lo) else lo, None if pd.isna(hi) else hi, None if pd.isna(c) else c, None if pd.isna(p) else p)
           for lo, hi, c, p in zip(df.salary_min, df.salary_max, df.salary_currency, df.salary_period)]
    df["salary_min_usd"] = pd.to_numeric(pd.Series([u[0] for u in usd], index=df.index), errors="coerce")
    df["salary_max_usd"] = pd.to_numeric(pd.Series([u[1] for u in usd], index=df.index), errors="coerce")
    df["salary_mid_usd"] = (df["salary_min_usd"] + df["salary_max_usd"]) / 2
    df["has_salary"] = df["salary_mid_usd"].notna()

    df["posted_at"] = pd.to_datetime(df["posted_at"], errors="coerce")
    df["month"] = df["posted_at"].dt.to_period("M").astype(str).astype(object).where(df["posted_at"].notna(), None)
    df["text"] = (df["title"] + "\n" + df["tags"].fillna("").astype(str).str.replace("|", " ") + "\n" + df["description"])
    return df.reset_index(drop=True)
