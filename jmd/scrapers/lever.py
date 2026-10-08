"""Lever postings API (https://api.lever.co/v0/postings/<company>?mode=json). Some postings carry salaryRange."""
from __future__ import annotations

from datetime import datetime, timezone

from ..schema import JobPosting
from .base import get_json, is_data_role, log, make_id, strip_html

NAME = "lever"
URL = "https://api.lever.co/v0/postings/{company}"

COMPANIES = [
    "netflix", "spotify", "shopify", "atlassian", "palantir", "nvidia", "dataiku", "mistral",
    "wealthsimple", "faire", "whoop", "clever", "lucidmotors", "kraken", "rippling",
    "quora", "carta", "benchling", "upstart", "attentive", "verkada", "outreach",
]

_INTERVAL = {"per-year-salary": "year", "per-month-salary": "month", "per-hour-wage": "hour", "per-day": "day"}


def parse(payload: list[dict], company: str) -> list[JobPosting]:
    out = []
    for item in payload:
        title = item.get("text") or ""
        if not is_data_role(title):
            continue
        cats = item.get("categories") or {}
        sr = item.get("salaryRange") or {}
        lists = "\n".join(f"{l.get('text','')}\n{strip_html(l.get('content'))}" for l in item.get("lists", []))
        desc = "\n".join(x for x in (item.get("descriptionPlain") or strip_html(item.get("description")), lists,
                                     item.get("additionalPlain") or "") if x)
        ts = item.get("createdAt")
        out.append(JobPosting(
            id=make_id(NAME, f"{company}-{item.get('id')}"),
            source=NAME,
            url=item.get("hostedUrl") or "",
            title=title,
            company=company.title(),
            location=cats.get("location") or cats.get("allLocations", [""])[0] if cats else "",
            remote=("remote" in (cats.get("location") or "").lower()) or None,
            posted_at=datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat() if ts else None,
            salary_min=float(sr["min"]) if sr.get("min") else None,
            salary_max=float(sr["max"]) if sr.get("max") else None,
            salary_currency=sr.get("currency") if sr else None,
            salary_period=_INTERVAL.get(sr.get("interval", ""), "year") if sr else None,
            description=desc,
            tags=[cats.get("team", ""), cats.get("commitment", ""), cats.get("department", "")],
        ))
    return out


def fetch(limit: int = 5000, query: str | None = None) -> list[JobPosting]:
    companies = [c.strip() for c in query.split(",")] if query else COMPANIES
    out: list[JobPosting] = []
    for company in companies:
        try:
            payload = get_json(URL.format(company=company), params={"mode": "json"})
        except Exception as exc:
            log.warning("lever company %s skipped: %s", company, exc)
            continue
        batch = parse(payload, company)
        log.info("%s/%s: %d data roles", NAME, company, len(batch))
        out.extend(batch)
        if len(out) >= limit:
            break
    return out[:limit]
