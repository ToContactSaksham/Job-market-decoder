"""'What should I learn next?' recommendation engine.

Given the skills a person already has (and optionally a target role / city), score
every other skill on four signals computed from the market data:

  demand    - share of target-segment postings that ask for the skill
  pay       - adjusted salary premium (regression coefficient), clipped to [-10%, +25%]
  adjacency - how often the skill co-occurs with skills the person already has
              (a proxy for "how natural is the next step"); mean lift vs. have-set
  unlock    - share of target-segment postings the person would newly qualify for
              (>= 70% of required skills covered) after adding the skill

Each signal is scaled to [0, 1] across candidates and combined with weights that
the caller can change. A rarity bonus rewards skills that are well paid but still
uncommon (the "rare combo" angle), since those are where a learner has an edge.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .analysis import adjusted_premiums, lift_matrix

DEFAULT_WEIGHTS = {"demand": 0.35, "pay": 0.25, "adjacency": 0.15, "unlock": 0.25}
QUALIFY_THRESHOLD = 0.6
SOFT_CATEGORIES = ("domain_soft",)


@dataclass
class Recommendation:
    skill: str
    category: str
    score: float
    demand_share: float
    premium_pct: float | None
    adjacency: float
    unlock_pct: float
    rarity_bonus: float
    reasons: list[str] = field(default_factory=list)


class Recommender:
    def __init__(self, X: pd.DataFrame, df: pd.DataFrame, category: dict[str, str] | None = None,
                 premiums: pd.DataFrame | None = None, weights: dict | None = None):
        self.X, self.df = X, df
        self.category = category or {}
        self.premiums = premiums if premiums is not None else adjusted_premiums(X, df)
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        self._lift = lift_matrix(X, list(X.columns))

    # --------------------------------------------------------------
    def _segment(self, role: str | None, city: str | None) -> np.ndarray:
        m = np.ones(len(self.df), dtype=bool)
        if role:
            m &= (self.df["role"] == role).to_numpy()
        if city:
            m &= (self.df["city"] == city).to_numpy()
        if m.sum() < 50:  # too thin: fall back to the whole market
            m = np.ones(len(self.df), dtype=bool)
        return m

    def normalise_have(self, have: list[str]) -> list[str]:
        lookup = {s.lower(): s for s in self.X.columns}
        out = []
        for h in have:
            k = h.strip().lower()
            if k in lookup:
                out.append(lookup[k])
            else:
                hits = [s for s in self.X.columns if k and (k in s.lower() or s.lower() in k)]
                if hits:
                    out.append(hits[0])
        return list(dict.fromkeys(out))

    def recommend(self, have: list[str], role: str | None = None, city: str | None = None, top: int = 10,
                  exclude_categories: tuple[str, ...] = ("domain_soft",)) -> list[Recommendation]:
        have = self.normalise_have(have)
        seg = self._segment(role, city)
        Xs = self.X[seg]
        n = len(Xs)
        candidates = [s for s in self.X.columns if s not in have and self.category.get(s) not in exclude_categories]

        demand = Xs[candidates].mean()
        prem = self.premiums["premium_pct"].reindex(candidates)
        pay = prem.clip(-10, 25).fillna(0)

        if have:
            adjacency = self._lift.loc[candidates, have].mean(axis=1).fillna(1.0)
        else:
            adjacency = pd.Series(1.0, index=candidates)

        # Unlock: postings where the person already covers >= threshold of hard skills, after adding candidate.
        hard = [c for c in Xs.columns if self.category.get(c) not in SOFT_CATEGORIES]
        Xs = Xs[hard]
        req = Xs.to_numpy()
        n_req = req.sum(axis=1)
        have_idx = [Xs.columns.get_loc(h) for h in have if h in Xs.columns]
        covered = req[:, have_idx].sum(axis=1) if have_idx else np.zeros(n)
        with np.errstate(divide="ignore", invalid="ignore"):
            qualified_now = np.where(n_req > 0, covered / np.maximum(n_req, 1) >= QUALIFY_THRESHOLD, False)
        unlock = {}
        for c in candidates:
            cov = covered + req[:, Xs.columns.get_loc(c)]
            q = np.where(n_req > 0, cov / np.maximum(n_req, 1) >= QUALIFY_THRESHOLD, False)
            unlock[c] = (q & ~qualified_now).mean()
        unlock = pd.Series(unlock)

        def scale(s: pd.Series) -> pd.Series:
            s = s.astype(float)
            rng = s.max() - s.min()
            return (s - s.min()) / rng if rng > 0 else s * 0

        rarity = ((prem.fillna(0) > 3) & (demand >= 0.01) & (demand < 0.15)) * np.log1p(1 / np.maximum(demand, 1e-3)) / np.log1p(1000)
        score = (self.weights["demand"] * scale(demand) + self.weights["pay"] * scale(pay)
                 + self.weights["adjacency"] * scale(np.log(adjacency.clip(lower=0.1)))
                 + self.weights["unlock"] * scale(unlock) + 0.1 * rarity)

        out = []
        for s in score.sort_values(ascending=False).head(top).index:
            p = prem.get(s)
            reasons = [f"asked for in {demand[s]:.0%} of {'target' if (role or city) else 'all'} postings"]
            if p is not None and not np.isnan(p):
                reasons.append(f"{'+' if p >= 0 else ''}{p:.1f}% adjusted pay premium")
            if have and adjacency[s] > 1.3:
                reasons.append(f"{adjacency[s]:.1f}x more likely alongside skills you have")
            if unlock[s] > 0.005:
                reasons.append(f"unlocks {unlock[s]:.1%} more postings")
            if rarity[s] > 0:
                reasons.append("rare but well-paid")
            out.append(Recommendation(skill=s, category=self.category.get(s, ""), score=float(score[s]), demand_share=float(demand[s]),
                                      premium_pct=None if p is None or np.isnan(p) else float(p), adjacency=float(adjacency[s]),
                                      unlock_pct=float(unlock[s]), rarity_bonus=float(rarity[s]), reasons=reasons))
        return out

    def coverage(self, have: list[str], role: str | None = None, city: str | None = None) -> dict:
        """How much of the target segment the person already qualifies for."""
        have = self.normalise_have(have)
        seg = self._segment(role, city)
        Xs = self.X[seg]
        Xs = Xs[[c for c in Xs.columns if self.category.get(c) not in SOFT_CATEGORIES]]
        req = Xs.to_numpy()
        n_req = req.sum(axis=1)
        idx = [Xs.columns.get_loc(h) for h in have if h in Xs.columns]
        covered = req[:, idx].sum(axis=1) if idx else np.zeros(len(Xs))
        ratio = np.where(n_req > 0, covered / np.maximum(n_req, 1), 0)
        return {"postings": int(seg.sum()), "qualified_share": float((ratio >= QUALIFY_THRESHOLD).mean()),
                "mean_coverage": float(ratio.mean()), "have": have}

    def learning_path(self, have: list[str], role: str | None = None, city: str | None = None, steps: int = 5) -> list[Recommendation]:
        """Greedy sequence: pick the top recommendation, add it to the have-set, repeat."""
        path, cur = [], list(have)
        for _ in range(steps):
            recs = self.recommend(cur, role, city, top=1)
            if not recs:
                break
            path.append(recs[0])
            cur.append(recs[0].skill)
        return path


def to_frame(recs: list[Recommendation]) -> pd.DataFrame:
    return pd.DataFrame([{"skill": r.skill, "category": r.category, "score": round(r.score, 3), "demand_share": round(r.demand_share, 3),
                          "premium_pct": None if r.premium_pct is None else round(r.premium_pct, 1), "adjacency": round(r.adjacency, 2),
                          "unlock_pct": round(r.unlock_pct * 100, 2), "why": "; ".join(r.reasons)} for r in recs])
