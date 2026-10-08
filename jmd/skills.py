"""Skill extraction: regex taxonomy matching plus light NLP for discovering candidate skills we do not know yet."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yaml

from . import config


@dataclass
class Skill:
    name: str
    category: str
    patterns: list[re.Pattern]

    def matches(self, text: str) -> bool:
        return any(p.search(text) for p in self.patterns)

    def count(self, text: str) -> int:
        return sum(len(p.findall(text)) for p in self.patterns)


def load_taxonomy(path=config.TAXONOMY_PATH) -> list[Skill]:
    raw = yaml.safe_load(open(path, encoding="utf-8"))
    skills = []
    for category, entries in raw.items():
        for name, pats in entries.items():
            # Merge patterns into (at most) one case-insensitive and one case-sensitive regex per skill.
            ci = [p for p in pats if not p.startswith("(?-i)")]
            cs = [p[5:] for p in pats if p.startswith("(?-i)")]
            compiled = []
            if ci:
                compiled.append(re.compile("|".join(f"(?:{p})" for p in ci), re.I))
            if cs:
                compiled.append(re.compile("|".join(f"(?:{p})" for p in cs)))
            skills.append(Skill(str(name), category, compiled))
    return skills


class SkillExtractor:
    """Builds a boolean posting x skill matrix from free text.

    Matching is done on a lightly normalised copy of the text: zero-width/odd
    whitespace removed, but case preserved so case-sensitive patterns (R, SAS, Go)
    keep working.
    """

    def __init__(self, skills: list[Skill] | None = None):
        self.skills = skills or load_taxonomy()
        self.names = [s.name for s in self.skills]
        self.category = {s.name: s.category for s in self.skills}

    @staticmethod
    def normalise(text: str) -> str:
        text = re.sub(r"[​ ]", " ", text or "")
        text = re.sub(r"[•·▪◦]", "\n", text)
        return text

    def extract(self, text: str) -> list[str]:
        t = self.normalise(text)
        return [s.name for s in self.skills if s.matches(t)]

    def matrix(self, texts: pd.Series) -> pd.DataFrame:
        rows = [[s.matches(t) for s in self.skills] for t in texts.map(self.normalise)]
        return pd.DataFrame(np.array(rows, dtype=bool), columns=self.names, index=texts.index)

    def requirement_strength(self, text: str) -> dict[str, str]:
        """Classify each matched skill as 'required' or 'nice-to-have' using section headers."""
        t = self.normalise(text)
        nice_start = None
        m = re.search(r"(?im)^\W*(?:nice[\s\-]to[\s\-]have|bonus|preferred(?: qualifications)?|plus(?:es)?)\b.*$", t)
        if m:
            nice_start = m.start()
        out = {}
        for s in self.skills:
            hits = [p.search(t) for p in s.patterns]
            hits = [h for h in hits if h]
            if not hits:
                continue
            first = min(h.start() for h in hits)
            out[s.name] = "nice-to-have" if (nice_start is not None and first >= nice_start) else "required"
        return out


# ----------------------------------------------------------------------------
# Discovery: find frequent capitalised tokens / bigrams that are NOT in the
# taxonomy. These are candidate skills to add to skills.yaml.
# ----------------------------------------------------------------------------
_STOP = set("""a an the and or of to in for with on at by from as is are be we you our your this that will who what
experience years year team work working strong ability skills skill knowledge required preferred plus role job
company data business product engineering analytics science analysis analyst engineer scientist senior junior lead
including include across using use used build building develop developing support ensure drive help new best
across between within without more than other all any some such their they them it its""".split())
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,30}")
_BOUNDARY = re.compile(r"(?:^|[.!?:;\n]\s*|^\s*[-•*]\s*|\n\s*[-•*]\s*)$")


def _tokens(text: str) -> list[tuple[str, bool]]:
    """(token, at_sentence_start) pairs; trailing punctuation stripped."""
    out = []
    for m in _TOKEN.finditer(text):
        tok = m.group().rstrip(".,;:")
        if len(tok) < 2:
            continue
        start = bool(_BOUNDARY.search(text[max(0, m.start() - 4):m.start()])) or m.start() == 0
        out.append((tok, start))
    return out


def discover_candidates(texts: pd.Series, extractor: SkillExtractor, top: int = 60, min_docs: int = 20) -> pd.DataFrame:
    """Return frequent tech-looking tokens and bigrams not covered by the taxonomy."""
    known = re.compile("|".join(p.pattern for s in extractor.skills for p in s.patterns), re.I)
    doc_uni, doc_bi = Counter(), Counter()
    n = 0
    for text in texts:
        n += 1
        pairs = [(t, st) for t, st in _tokens(extractor.normalise(text)) if t.lower() not in _STOP]
        toks = [t for t, _ in pairs]
        techy = lambda t: any(c in t for c in "+#.") or any(c.isdigit() for c in t) or (t.isupper() and 2 <= len(t) <= 6) \
            or (t[0].isupper() and any(c.isupper() for c in t[1:]))
        uni = {t for t, st in pairs if (techy(t) or (t[0].isupper() and not st)) and len(t) > 2 and not known.search(t)}
        bi = {f"{a} {b}" for (a, sa), (b, _) in zip(pairs, pairs[1:]) if a[0].isupper() and b[0].isupper() and not sa and not known.search(f"{a} {b}")}
        doc_uni.update(uni)
        doc_bi.update(bi)
    rows = [(k, v, "unigram") for k, v in doc_uni.items() if v >= min_docs] + [(k, v, "bigram") for k, v in doc_bi.items() if v >= min_docs]
    df = pd.DataFrame(rows, columns=["candidate", "postings", "kind"])
    df["share"] = df["postings"] / max(n, 1)
    return df.sort_values("postings", ascending=False).head(top).reset_index(drop=True)
