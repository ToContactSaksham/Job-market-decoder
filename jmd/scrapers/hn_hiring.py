"""Hacker News "Who is hiring?" threads via the Algolia HN API.

Each top-level comment is one posting, conventionally formatted as
`Company | Role | Location | ONSITE/REMOTE | Salary | ...`. We parse the pipe
header heuristically and keep the whole comment as the description.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from ..schema import JobPosting
from .base import get_json, is_data_role, log, make_id, strip_html

NAME = "hn_hiring"
SEARCH = "https://hn.algolia.com/api/v1/search"
SEARCH_BY_DATE = "https://hn.algolia.com/api/v1/search_by_date"

_SAL = re.compile(r"(?:[$€£]\s?\d{2,3}\s?k|\d{2,3}\s?k\s?[-–]\s?\d{2,3}\s?k|\$\d{3},\d{3})", re.I)


def find_threads(months: int = 6) -> list[dict]:
    payload = get_json(SEARCH, params={"query": "Ask HN: Who is hiring?", "tags": "story,author_whoishiring",
                                       "hitsPerPage": months})
    return [h for h in payload.get("hits", []) if "who is hiring" in (h.get("title") or "").lower()]


def parse_comments(payload: dict, thread_title: str = "") -> list[JobPosting]:
    out = []
    for hit in payload.get("hits", []):
        text = strip_html(hit.get("comment_text"))
        if not text:
            continue
        header = text.split("\n", 1)[0]
        parts = [p.strip() for p in header.split("|")]
        company = parts[0][:80] if parts else ""
        role_bits = [p for p in parts[1:] if is_data_role(p)]
        if not role_bits and not is_data_role(header):
            continue
        title = role_bits[0] if role_bits else next((p for p in parts[1:] if p), header[:80])
        remote = "REMOTE" in header.upper()
        location = next((p for p in parts[1:] if re.search(r"[A-Z][a-z]+,\s*[A-Z]{2}|London|Berlin|Remote|NYC|SF\b", p)), "")
        ts = hit.get("created_at_i")
        out.append(JobPosting(
            id=make_id(NAME, hit.get("objectID")),
            source=NAME,
            url=f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
            title=title,
            company=company,
            location=location or ("Remote" if remote else ""),
            remote=remote or None,
            posted_at=datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if ts else None,
            description=text,
            tags=[thread_title],
        ))
    return out


def fetch(limit: int = 3000, query: str | None = None) -> list[JobPosting]:
    out: list[JobPosting] = []
    for thread in find_threads(months=int(query) if query and query.isdigit() else 6):
        sid = thread.get("objectID")
        page = 0
        while True:
            payload = get_json(SEARCH_BY_DATE, params={"tags": f"comment,story_{sid}", "hitsPerPage": 1000, "page": page})
            batch = parse_comments(payload, thread.get("title", ""))
            out.extend(batch)
            log.info("%s %s page %d: %d data roles", NAME, thread.get("title"), page, len(batch))
            page += 1
            if page >= payload.get("nbPages", 1) or len(out) >= limit:
                break
    return out[:limit]
