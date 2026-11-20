import datetime as dt
import json

import pytest

from trendwaves import archive, metadata


def test_batches_respect_query_limit():
    repos = [f"some-owner-{i}/a-fairly-long-repository-name-{i}" for i in range(50)]
    groups = metadata.batches(repos)
    assert sum(len(g) for g in groups) == 50
    for g in groups:
        assert len(" ".join(f"repo:{r}" for r in g)) <= metadata.MAX_QUERY_CHARS


def test_load_day_from_cache(tmp_path):
    day = dt.date(2026, 3, 1)
    (tmp_path / f"{day}.json").write_text(json.dumps({"date": str(day), "list": ["a/b", "bad", "c/d"]}))
    assert archive.load_day(day, tmp_path, offline=True) == ["a/b", "c/d"]
    assert archive.load_day(dt.date(2026, 3, 2), tmp_path, offline=True) is None


def test_corrupt_day_raises(tmp_path):
    day = dt.date(2026, 3, 1)
    (tmp_path / f"{day}.json").write_text(json.dumps({"date": "2020-01-01", "list": []}))
    with pytest.raises(ValueError):
        archive.load_day(day, tmp_path, offline=True)


def test_fetch_offline_records_missing(tmp_path):
    day = dt.date(2026, 3, 1)
    (tmp_path / f"{day}.json").write_text(json.dumps({"date": str(day), "list": ["a/b"]}))
    res = archive.fetch(day, day + dt.timedelta(days=1), tmp_path, offline=True)
    assert list(res.days) == [day] and res.missing == [day + dt.timedelta(days=1)]
