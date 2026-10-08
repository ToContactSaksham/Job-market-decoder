"""Arbeitnow job board API (https://www.arbeitnow.com/api/job-board-api). Paginated, mostly EU/remote."""
from __future__ import annotations

from datetime import datetime, timezone

from ..schema import JobPosting
from .base import get_json, is_data_role, log, make_id, strip_html

NAME = "arbeitnow"
URL = "https://www.arbeitnow.com/api/job-board-api"


def parse(payload: dict) -> list[JobPosting]:
    out = []
    for item in payload.get("data", []):
        title = item.get("title") or ""
        if not is_data_role(title):
            continue
        ts = item.get("created_at")
        out.append(JobPosting(
            id=make_id(NAME, item.get("slug")),
            source=NAME,
            url=item.get("url") or "",
            title=title,
            company=item.get("company_name") or "",
            location=item.get("location") or "",
            remote=bool(item.get("remote")),
            posted_at=datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if ts else None,
            description=strip_html(item.get("description")),
            tags=list(item.get("tags", [])) + list(item.get("job_types", [])),
        ))
    return out


def fetch(limit: int = 2000, query: str | None = None, max_pages: int = 60) -> list[JobPosting]:
    out: list[JobPosting] = []
    page = 1
    while len(out) < limit and page <= max_pages:
        payload = get_json(URL, params={"page": page})
        batch = parse(payload)
        out.extend(batch)
        log.info("%s page %d: %d data roles (total %d)", NAME, page, len(batch), len(out))
        if not payload.get("links", {}).get("next"):
            break
        page += 1
    return out[:limit]
