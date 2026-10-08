"""Scraper registry. Every scraper exposes `fetch(limit, query) -> list[JobPosting]`."""
from __future__ import annotations

from . import remoteok, arbeitnow, remotive, jobicy, greenhouse, lever, hn_hiring

SCRAPERS = {
    "remoteok": remoteok,
    "arbeitnow": arbeitnow,
    "remotive": remotive,
    "jobicy": jobicy,
    "greenhouse": greenhouse,
    "lever": lever,
    "hn_hiring": hn_hiring,
}
