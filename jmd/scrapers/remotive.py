"""Remotive public API (https://remotive.com/api/remote-jobs). Has a `data` category and salary strings."""
from __future__ import annotations

from ..schema import JobPosting
from .base import get_json, is_data_role, make_id, strip_html

NAME = "remotive"
URL = "https://remotive.com/api/remote-jobs"


def parse(payload: dict) -> list[JobPosting]:
    out = []
    for item in payload.get("jobs", []):
        title = item.get("title") or ""
        if not (is_data_role(title) or item.get("category") == "Data Analysis"):
            continue
        salary_text = item.get("salary") or ""
        desc = strip_html(item.get("description"))
        if salary_text:
            desc = f"Salary: {salary_text}\n{desc}"  # let the salary parser pick it up from text
        out.append(JobPosting(
            id=make_id(NAME, item.get("id")),
            source=NAME,
            url=item.get("url") or "",
            title=title,
            company=item.get("company_name") or "",
            location=item.get("candidate_required_location") or "Remote",
            remote=True,
            posted_at=(item.get("publication_date") or "")[:10] or None,
            description=desc,
            tags=list(item.get("tags", [])) + [item.get("job_type") or ""],
        ))
    return out


def fetch(limit: int = 2000, query: str | None = None) -> list[JobPosting]:
    out: list[JobPosting] = []
    for cat in ("data", "software-dev", "product", "finance-legal"):
        payload = get_json(URL, params={"category": cat, "limit": limit})
        out.extend(parse(payload))
    if query:
        out.extend(parse(get_json(URL, params={"search": query, "limit": limit})))
    seen, dedup = set(), []
    for p in out:
        if p.id not in seen:
            seen.add(p.id); dedup.append(p)
    return dedup[:limit]
