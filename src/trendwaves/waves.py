"""Detect "heat waves": stretches of days when a topic is well above its normal level.

A wave for a category is a run of days where its smoothed daily points exceed

    threshold = max(min_points, mean + z * std)

(mean/std of that category's smoothed series over the whole period). Runs separated
by at most ``merge_gap`` days are merged, and runs shorter than ``min_days`` are
dropped. Each wave reports when it started, peaked and ended, how high it got and
which repositories carried it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass
class Wave:
    level: str  # "topic" or "subtopic"
    category: str
    start: pd.Timestamp
    peak: pd.Timestamp
    end: pd.Timestamp
    days: int
    peak_points: float  # smoothed points/day at the peak
    peak_share: float  # share of all points that day (smoothed)
    baseline_points: float  # the category's mean smoothed points/day
    lift: float  # peak_points / baseline_points
    wave_points: float  # raw points earned during the wave
    top_repositories: str  # "owner/name (pts); ..."
    lead_repository: str

    def as_row(self) -> dict:
        d = asdict(self)
        for k in ("start", "peak", "end"):
            d[k] = d[k].date()
        return d


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    runs, start = [], None
    for i, flag in enumerate(mask):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs


def _merge(runs: list[tuple[int, int]], gap: int) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for s, e in runs:
        if merged and s - merged[-1][1] - 1 <= gap:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def detect(
    smoothed: pd.DataFrame,
    shares: pd.DataFrame,
    table: pd.DataFrame,
    key: str,
    level: str,
    z: float = 0.75,
    min_points: float = 3.0,
    min_days: int = 5,
    merge_gap: int = 3,
    top_k: int = 3,
    skip: tuple[str, ...] = ("Other", "Unclassified"),
) -> list[Wave]:
    waves: list[Wave] = []
    for cat in smoothed.columns:
        if cat in skip:
            continue
        s = smoothed[cat]
        valid = s.dropna()
        if valid.empty:
            continue
        mean, std = float(valid.mean()), float(valid.std(ddof=0))
        threshold = max(min_points, mean + z * std)
        mask = (s.fillna(0) > threshold).to_numpy()
        for a, b in _merge(_runs(mask), merge_gap):
            if b - a + 1 < min_days:
                continue
            window = s.iloc[a : b + 1]
            peak = window.idxmax()
            start, end = s.index[a], s.index[b]
            rows = table[(table[key] == cat) & (table["date"] >= start) & (table["date"] <= end)]
            per_repo = rows.groupby("repository")["points"].sum().sort_values(ascending=False)
            tops = per_repo.head(top_k)
            waves.append(
                Wave(
                    level=level,
                    category=cat,
                    start=start,
                    peak=peak,
                    end=end,
                    days=int(b - a + 1),
                    peak_points=round(float(window.max()), 2),
                    peak_share=round(float(shares.loc[peak, cat]), 4) if cat in shares else float("nan"),
                    baseline_points=round(mean, 2),
                    lift=round(float(window.max()) / mean, 2) if mean else float("nan"),
                    wave_points=round(float(rows["points"].sum()), 1),
                    top_repositories="; ".join(f"{r} ({p:g})" for r, p in tops.items()),
                    lead_repository=tops.index[0] if len(tops) else "",
                )
            )
    waves.sort(key=lambda w: (w.start, w.category))
    return waves


def to_frame(waves: list[Wave]) -> pd.DataFrame:
    cols = list(Wave.__dataclass_fields__)
    return pd.DataFrame([w.as_row() for w in waves], columns=cols)


def momentum(smoothed_raw: pd.DataFrame, recent: int = 14, prior: int = 56) -> pd.DataFrame:
    """Compare the last ``recent`` days with the ``prior`` days before them (raw daily points)."""
    data = smoothed_raw.dropna(how="all")
    if len(data) < recent + 1:
        return pd.DataFrame(columns=["category", "recent_avg", "prior_avg", "change"])
    last = data.iloc[-recent:].mean()
    before = data.iloc[-(recent + prior) : -recent].mean()
    out = pd.DataFrame({"recent_avg": last.round(2), "prior_avg": before.round(2)})
    out["change"] = (out["recent_avg"] - out["prior_avg"]).round(2)
    out.index.name = "category"
    return out.sort_values("change", ascending=False).reset_index()
