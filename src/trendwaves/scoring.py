"""Turn daily rankings into points and aggregate them by topic."""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pandas as pd

from .archive import source_url
from .taxonomy import Label

# A scheme maps (rank, top_n) -> points. rank is 1-based.
SCHEMES: dict[str, Callable[[int, int], float]] = {
    # 1st = N points, 2nd = N-1, ..., Nth = 1  (N=10 -> 55 points per day)
    "linear": lambda rank, n: float(n + 1 - rank),
    # 1st = 1, 2nd = 1/2, 3rd = 1/3, ... (rewards the very top)
    "reciprocal": lambda rank, n: 1.0 / rank,
    # every listed repo counts the same (pure "presence")
    "flat": lambda rank, n: 1.0,
}


def rank_table(days: dict[dt.date, list[str]], top_n: int, scheme: str) -> pd.DataFrame:
    """One row per (date, rank, repository) with its points."""
    if scheme not in SCHEMES:
        raise ValueError(f"unknown scoring scheme {scheme!r}; choose from {sorted(SCHEMES)}")
    fn = SCHEMES[scheme]
    rows = []
    for day, repos in days.items():
        for rank, repo in enumerate(repos[:top_n], start=1):
            rows.append({"date": pd.Timestamp(day), "rank": rank, "repository": repo, "points": fn(rank, top_n)})
    return pd.DataFrame(rows, columns=["date", "rank", "repository", "points"])


def attach_labels(table: pd.DataFrame, labels: dict[str, Label]) -> pd.DataFrame:
    t = table.copy()
    t["topic"] = t["repository"].map(lambda r: labels[r].topic)
    t["subtopic"] = t["repository"].map(lambda r: labels[r].subtopic)
    t["classification_method"] = t["repository"].map(lambda r: labels[r].method)
    t["github_url"] = "https://github.com/" + t["repository"]
    t["source_url"] = t["date"].map(lambda d: source_url(d.date()))
    return t


def daily_matrix(table: pd.DataFrame, key: str, dates: list[dt.date]) -> pd.DataFrame:
    """Dates x categories matrix of raw points. Days missing from the archive are NaN, not 0."""
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in dates], name="date")
    m = table.pivot_table(index="date", columns=key, values="points", aggfunc="sum", fill_value=0.0)
    m = m.reindex(idx)  # rows for loaded days; we fill zeros only on loaded days below
    loaded = set(table["date"].unique())
    m.loc[m.index.isin(loaded)] = m.loc[m.index.isin(loaded)].fillna(0.0)
    order = m.sum().sort_values(ascending=False).index
    return m[order]


def smooth(matrix: pd.DataFrame, window: int) -> pd.DataFrame:
    """Trailing mean over ``window`` days; missing days are skipped rather than counted as 0."""
    return matrix.rolling(window, min_periods=1).mean()


def share(matrix: pd.DataFrame) -> pd.DataFrame:
    """Each category's share of the day's total points (rows sum to 1)."""
    total = matrix.sum(axis=1).replace(0, float("nan"))
    return matrix.div(total, axis=0)


def repository_summary(table: pd.DataFrame, labels: dict[str, Label], meta: dict[str, dict]) -> pd.DataFrame:
    g = table.groupby("repository")
    out = pd.DataFrame(
        {
            "total_points": g["points"].sum(),
            "days_in_top": g["date"].nunique(),
            "best_rank": g["rank"].min(),
            "first_seen": g["date"].min().dt.date,
            "last_seen": g["date"].max().dt.date,
        }
    )
    out["topic"] = [labels[r].topic for r in out.index]
    out["subtopic"] = [labels[r].subtopic for r in out.index]
    out["classification_method"] = [labels[r].method for r in out.index]
    out["matched_text"] = [labels[r].matched for r in out.index]
    out["description"] = [(meta.get(r) or {}).get("description", "") for r in out.index]
    out["github_topics"] = ["; ".join((meta.get(r) or {}).get("topics", [])) for r in out.index]
    out["language"] = [(meta.get(r) or {}).get("language", "") for r in out.index]
    out["stars_now"] = [(meta.get(r) or {}).get("stars_now") for r in out.index]
    out.index.name = "repository"
    return out.sort_values(["total_points", "days_in_top"], ascending=False)
