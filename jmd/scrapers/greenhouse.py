"""Greenhouse job boards (https://boards-api.greenhouse.io/v1/boards/<board>/jobs?content=true).

Thousands of companies host their careers page on Greenhouse; the board slug is
usually the company name. Edit BOARDS (or pass --query board1,board2) to target
specific companies. Each board tells us the company, so company-size enrichment
works well for this source.
"""
from __future__ import annotations

import html as htmllib

from ..schema import JobPosting
from .base import get_json, is_data_role, log, make_id, strip_html

NAME = "greenhouse"
URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"

BOARDS = [
    "airbnb", "stripe", "coinbase", "databricks", "dropbox", "figma", "instacart", "lyft",
    "pinterest", "reddit", "robinhood", "doordash", "duolingo", "discord", "gitlab",
    "hashicorp", "cloudflare", "datadog", "mongodb", "elastic", "twilio", "zapier",
    "asana", "affirm", "brex", "chime", "flexport", "gusto", "notion", "nuro", "oscar",
    "plaid", "ramp", "samsara", "scaleai", "sofi", "squarespace", "toast", "wayfair",
    "zillow", "anthropic", "openai", "hudsonrivertrading", "janestreet", "twosigma",
]


def parse(payload: dict, board: str) -> list[JobPosting]:
    out = []
    for item in payload.get("jobs", []):
        title = item.get("title") or ""
        if not is_data_role(title):
            continue
        content = htmllib.unescape(item.get("content") or "")
        out.append(JobPosting(
            id=make_id(NAME, f"{board}-{item.get('id')}"),
            source=NAME,
            url=item.get("absolute_url") or "",
            title=title,
            company=(item.get("company_name") or board).title(),
            location=(item.get("location") or {}).get("name") or "",
            remote=None,
            posted_at=(item.get("updated_at") or item.get("first_published") or "")[:10] or None,
            description=strip_html(content),
            tags=[d.get("name", "") for d in item.get("departments", []) if d],
        ))
    return out


def fetch(limit: int = 5000, query: str | None = None) -> list[JobPosting]:
    boards = [b.strip() for b in query.split(",")] if query else BOARDS
    out: list[JobPosting] = []
    for board in boards:
        try:
            payload = get_json(URL.format(board=board), params={"content": "true"})
        except Exception as exc:  # a missing board is a 404; keep going
            log.warning("greenhouse board %s skipped: %s", board, exc)
            continue
        batch = parse(payload, board)
        log.info("%s/%s: %d data roles", NAME, board, len(batch))
        out.extend(batch)
        if len(out) >= limit:
            break
    return out[:limit]
