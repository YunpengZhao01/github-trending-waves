"""Daily GitHub Trending snapshots from the community archive.

Source: https://github.com/antonkomarev/github-trending-archive
Each day is stored as ``archive/repository/YYYY/YYYY-MM-DD/(null).json`` where
``(null)`` means "all languages". The file contains ``{"date": ..., "list": [...]}``
with repositories in Trending order.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import logging
import pathlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

SOURCE_REPO = "https://github.com/antonkomarev/github-trending-archive"
RAW_BASE = "https://raw.githubusercontent.com/antonkomarev/github-trending-archive/master/archive/repository"


def source_url(day: dt.date) -> str:
    return f"{SOURCE_REPO}/blob/master/archive/repository/{day.year}/{day}/(null).json"


def raw_url(day: dt.date) -> str:
    return f"{RAW_BASE}/{day.year}/{day}/(null).json"


def daterange(start: dt.date, end: dt.date):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


@dataclass
class ArchiveResult:
    days: dict[dt.date, list[str]] = field(default_factory=dict)  # date -> ranked repos
    missing: list[dt.date] = field(default_factory=list)  # 404 in the archive
    errors: dict[dt.date, str] = field(default_factory=dict)  # network / format errors


def _download(day: dt.date, retries: int = 3) -> bytes | None:
    req = urllib.request.Request(raw_url(day), headers={"User-Agent": "trendwaves"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(1.5 * (attempt + 1))
    return None


def _validate(day: dt.date, obj: object) -> list[str]:
    if not isinstance(obj, dict) or obj.get("date") != str(day) or not isinstance(obj.get("list"), list):
        raise ValueError(f"unexpected archive content for {day}")
    return [r for r in obj["list"] if isinstance(r, str) and "/" in r]


def load_day(day: dt.date, cache_dir: pathlib.Path, refresh: bool = False, offline: bool = False) -> list[str] | None:
    """Return the ranked repository list for one day (cached on disk)."""
    path = cache_dir / f"{day}.json"
    if path.exists() and not refresh:
        return _validate(day, json.loads(path.read_text(encoding="utf-8")))
    if offline:
        return None
    raw = _download(day)
    if raw is None:
        return None
    repos = _validate(day, json.loads(raw))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return repos


def fetch(
    start: dt.date,
    end: dt.date,
    cache_dir: pathlib.Path,
    refresh: bool = False,
    offline: bool = False,
    workers: int = 8,
) -> ArchiveResult:
    """Load every day in ``[start, end]``, downloading uncached days in parallel."""
    result = ArchiveResult()
    days = list(daterange(start, end))

    def task(day: dt.date):
        return day, load_day(day, cache_dir, refresh=refresh, offline=offline)

    with cf.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(task, d): d for d in days}
        for fut in cf.as_completed(futures):
            day = futures[fut]
            try:
                _, repos = fut.result()
            except Exception as exc:  # noqa: BLE001 - recorded in coverage report
                result.errors[day] = str(exc)
                log.warning("%s: %s", day, exc)
                continue
            if repos is None:
                result.missing.append(day)
            else:
                result.days[day] = repos
    result.missing.sort()
    result.days = dict(sorted(result.days.items()))
    log.info("Archive: %d days loaded, %d missing, %d errors", len(result.days), len(result.missing), len(result.errors))
    return result
