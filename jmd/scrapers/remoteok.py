"""RemoteOK public JSON feed (https://remoteok.com/api). One request returns every live posting."""
from __future__ import annotations

from datetime import datetime

from ..schema import JobPosting
from .base import get_json, is_data_role, make_id, strip_html

NAME = "remoteok"
URL = "https://remoteok.com/api"


def parse(payload: list[dict]) -> list[JobPosting]:
    out = []
    for item in payload:
        if not isinstance(item, dict) or "position" not in item:
            continue  # first element is a legal notice
        title = item.get("position") or ""
        tags = [t for t in item.get("tags", []) if t]
        if not (is_data_role(title) or {"data", "analytics", "data science"} & set(tags)):
            continue
        smin, smax = item.get("salary_min") or None, item.get("salary_max") or None
        out.append(JobPosting(
            id=make_id(NAME, item.get("id")),
            source=NAME,
            url=item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('slug','')}",
            title=title,
            company=item.get("company") or "",
            location=item.get("location") or "Remote",
            remote=True,
            posted_at=_date(item.get("date")),
            salary_min=float(smin) if smin else None,
            salary_max=float(smax) if smax else None,
            salary_currency="USD" if (smin or smax) else None,
            salary_period="year" if (smin or smax) else None,
            description=strip_html(item.get("description")),
            tags=tags,
        ))
    return out


def fetch(limit: int = 5000, query: str | None = None) -> list[JobPosting]:
    return parse(get_json(URL))[:limit]


def _date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None
