import datetime as dt

import numpy as np
import pandas as pd
import pytest

from trendwaves import scoring, waves
from trendwaves.taxonomy import Label

D = dt.date(2026, 1, 1)


def _days(n, top=10):
    return {D + dt.timedelta(i): [f"o/r{j}" for j in range(top + 5)] for i in range(n)}


@pytest.mark.parametrize("scheme, total", [("linear", 55), ("flat", 10), ("reciprocal", sum(1 / r for r in range(1, 11)))])
def test_points_per_day(scheme, total):
    t = scoring.rank_table(_days(1), 10, scheme)
    assert len(t) == 10
    assert t["points"].sum() == pytest.approx(total)


def test_unknown_scheme():
    with pytest.raises(ValueError):
        scoring.rank_table(_days(1), 10, "nope")


def test_missing_days_are_nan_not_zero():
    days = _days(3)
    del days[D + dt.timedelta(1)]
    t = scoring.rank_table(days, 10, "linear")
    labels = {r: Label("T", "S", "metadata") for r in t["repository"].unique()}
    t = scoring.attach_labels(t, labels)
    m = scoring.daily_matrix(t, "topic", [D + dt.timedelta(i) for i in range(3)])
    assert m["T"].iloc[0] == 55
    assert np.isnan(m["T"].iloc[1])
    # smoothing skips the gap instead of averaging in a zero
    assert scoring.smooth(m, 3)["T"].iloc[2] == 55


def test_wave_detection_finds_a_bump():
    idx = pd.date_range("2026-01-01", periods=120, freq="D")
    base = np.full(120, 5.0)
    base[40:60] = 30.0  # a 20-day wave
    raw = pd.DataFrame({"AI": base, "Web": np.full(120, 10.0)}, index=idx)
    table = pd.DataFrame(
        {"date": idx.repeat(1), "repository": "o/hot", "points": base, "subtopic": "AI"}
    )
    found = waves.detect(raw, scoring.share(raw), table, "subtopic", "subtopic", min_days=5)
    ai = [w for w in found if w.category == "AI"]
    assert len(ai) == 1
    w = ai[0]
    assert w.start == idx[40] and w.end == idx[59] and w.days == 20
    assert w.lead_repository == "o/hot"
    assert not [w for w in found if w.category == "Web"]  # a flat series has no waves


def test_merge_and_min_days():
    assert waves._merge([(0, 2), (4, 6), (20, 21)], gap=1) == [(0, 6), (20, 21)]
    assert waves._runs(np.array([0, 1, 1, 0, 1], dtype=bool)) == [(1, 2), (4, 4)]
