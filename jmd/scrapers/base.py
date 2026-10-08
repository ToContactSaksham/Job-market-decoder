"""Shared HTTP helpers for scrapers: polite rate-limiting, retries, HTML stripping, role filtering."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from ..schema import DATA_ROLE_PATTERNS

log = logging.getLogger("jmd.scrape")

USER_AGENT = (
    "job-market-decoder/0.1 (+https://github.com/ToContactSaksham/Job-market-decoder; "
    "educational data-analysis project)"
)
_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9"})

_ROLE_RE = re.compile("|".join(f"(?:{p})" for p in DATA_ROLE_PATTERNS.values()), re.I)


def get(url: str, *, params: dict | None = None, retries: int = 3, backoff: float = 2.0,
        min_interval: float = 1.0, timeout: float = 30.0) -> requests.Response:
    """GET with simple exponential backoff and a per-call minimum spacing."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = _session.get(url, params=params, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} from {url}", response=resp)
            resp.raise_for_status()
            time.sleep(min_interval)
            return resp
        except (requests.RequestException, requests.HTTPError) as exc:
            last_exc = exc
            wait = backoff ** attempt
            log.warning("request failed (%s); retry %d/%d in %.0fs", exc, attempt + 1, retries, wait)
            time.sleep(wait)
    raise RuntimeError(f"giving up on {url}: {last_exc}")


def get_json(url: str, **kw) -> Any:
    return get(url, **kw).json()


def strip_html(html: str | None) -> str:
    """Convert an HTML fragment to readable plain text (block elements -> newlines)."""
    if not html:
        return ""
    if "<" not in html:
        return _clean_ws(html)
    soup = BeautifulSoup(html, "lxml")
    for br in soup.find_all(["br", "p", "li", "div", "h1", "h2", "h3", "h4", "tr"]):
        br.insert_after("\n")
    return _clean_ws(soup.get_text(" "))


def _clean_ws(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def is_data_role(title: str) -> bool:
    return bool(_ROLE_RE.search(title or ""))


def make_id(source: str, raw_id: Any) -> str:
    return f"{source}:{raw_id}"
