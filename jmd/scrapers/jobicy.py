"""Jobicy remote jobs API (https://jobicy.com/api/v2/remote-jobs). Publishes annual salary ranges."""
from __future__ import annotations

from ..schema import JobPosting
from .base import get_json, is_data_role, make_id, strip_html

NAME = "jobicy"
URL = "https://jobicy.com/api/v2/remote-jobs"


def parse(payload: dict) -> list[JobPosting]:
    out = []
    for item in payload.get("jobs", []):
        title = item.get("jobTitle") or ""
        if not is_data_role(title):
            continue
        smin, smax = item.get("annualSalaryMin"), item.get("annualSalaryMax")
        out.append(JobPosting(
            id=make_id(NAME, item.get("id")),
            source=NAME,
            url=item.get("url") or "",
            title=title,
            company=item.get("companyName") or "",
            location=item.get("jobGeo") or "Remote",
            remote=True,
            posted_at=(item.get("pubDate") or "")[:10] or None,
            salary_min=float(smin) if smin else None,
            salary_max=float(smax) if smax else None,
            salary_currency=(item.get("salaryCurrency") or "USD") if (smin or smax) else None,
            salary_period="year" if (smin or smax) else None,
            description=strip_html(item.get("jobDescription") or item.get("jobExcerpt")),
            tags=list(item.get("jobIndustry", []) or []) + list(item.get("jobType", []) or []) + [item.get("jobLevel") or ""],
        ))
    return out


def fetch(limit: int = 1000, query: str | None = None) -> list[JobPosting]:
    out: list[JobPosting] = []
    for tag in ("data-science", "data-analyst", "data-engineer", "machine-learning", "business-intelligence", query or ""):
        if not tag:
            continue
        out.extend(parse(get_json(URL, params={"count": min(limit, 50), "tag": tag})))
    seen, dedup = set(), []
    for p in out:
        if p.id not in seen:
            seen.add(p.id); dedup.append(p)
    return dedup[:limit]
