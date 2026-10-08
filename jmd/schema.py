"""Canonical schema for a job posting, shared by every scraper and by the synthetic generator."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional

# Column order used for CSV/Parquet outputs.
COLUMNS = [
    "id", "source", "url", "title", "company", "location", "remote",
    "posted_at", "salary_min", "salary_max", "salary_currency", "salary_period",
    "company_size", "description", "tags",
]


@dataclass
class JobPosting:
    id: str                       # stable, source-prefixed id, e.g. "remoteok:123456"
    source: str                   # scraper name
    url: str
    title: str
    company: str
    location: str                 # raw location string as published
    description: str              # plain text (HTML stripped)
    remote: Optional[bool] = None
    posted_at: Optional[str] = None       # ISO-8601 date
    salary_min: Optional[float] = None    # as published; normalised later
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None # ISO code, e.g. USD
    salary_period: Optional[str] = None   # year | month | day | hour
    company_size: Optional[str] = None    # size bucket if the source publishes one
    tags: list[str] = field(default_factory=list)  # source-provided tags/keywords

    def to_row(self) -> dict:
        d = asdict(self)
        d["tags"] = "|".join(self.tags)
        return {k: d.get(k) for k in COLUMNS}


# Title keywords that identify a "data role". Used by scrapers to filter and by
# clean.py to assign a role family.
DATA_ROLE_PATTERNS = {
    "Data Scientist":        r"data scien|applied scien|research scien",
    "Data Analyst":          r"data analy|business analy|product analy|analytics analy|reporting analy|insights? analy|bi analy|marketing analy|financial analy",
    "Data Engineer":         r"data engineer|etl developer|data platform|pipeline engineer|data infrastructure",
    "ML Engineer":           r"machine learning|ml engineer|mlops|ai engineer|deep learning|nlp engineer|computer vision",
    "Analytics Engineer":    r"analytics engineer",
    "BI Developer":          r"\bbi developer|business intelligence|tableau developer|power ?bi developer|looker developer",
    "Data Architect":        r"data architect|database architect",
    "Database Administrator": r"\bdba\b|database admin",
    "Quantitative Analyst":  r"quant(?:itative)? (?:analyst|researcher|developer)|\bquant\b",
    "Data Manager":          r"head of data|director.*data|data (?:science )?manager|vp.*data|chief data|analytics manager|lead data",
}
