"""Repository metadata (description, topics, language, stars) from the GitHub API.

Metadata is fetched in *batches* through the search API (``repo:a/b repo:c/d ...``),
which needs ~10x fewer requests than one REST call per repository. Repositories the
search API does not return (renamed, deleted, private) fall back to the REST API.
Results are cached in ``<cache>/github_metadata.json`` and reused across runs.
"""
from __future__ import annotations

import json
import logging
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable

log = logging.getLogger(__name__)

API = "https://api.github.com"
USER_AGENT = "trendwaves (+https://github.com/)"
MAX_QUERY_CHARS = 250  # GitHub rejects search queries longer than 256 characters


def _request(url: str, token: str | None) -> tuple[int, dict | None, dict]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = None
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - body is optional diagnostics only
            pass
        return exc.code, body, dict(exc.headers or {})


def _wait_for_reset(headers: dict, default: float = 60.0) -> None:
    reset = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")
    retry = headers.get("Retry-After") or headers.get("retry-after")
    if retry:
        delay = float(retry)
    elif reset:
        delay = max(1.0, float(reset) - time.time() + 1)
    else:
        delay = default
    delay = min(delay, 900.0)
    log.warning("GitHub rate limit reached; sleeping %.0fs", delay)
    time.sleep(delay)


def _record(item: dict) -> dict:
    return {
        "full_name": item.get("full_name", ""),
        "description": item.get("description") or "",
        "topics": item.get("topics") or [],
        "language": item.get("language") or "",
        "stars_now": item.get("stargazers_count"),
        "created_at": item.get("created_at") or "",
        "archived": bool(item.get("archived", False)),
    }


def batches(repos: Iterable[str], max_chars: int = MAX_QUERY_CHARS) -> list[list[str]]:
    """Group repositories so that each ``repo:`` search query stays under the length limit."""
    out: list[list[str]] = []
    cur: list[str] = []
    length = 0
    for repo in repos:
        term = len("repo:") + len(repo) + 1
        if cur and length + term > max_chars:
            out.append(cur)
            cur, length = [], 0
        cur.append(repo)
        length += term
    if cur:
        out.append(cur)
    return out


def _search_batch(batch: list[str], token: str | None, retries: int = 4) -> dict[str, dict]:
    query = " ".join(f"repo:{r}" for r in batch)
    url = f"{API}/search/repositories?" + urllib.parse.urlencode({"q": query, "per_page": 100})
    for _ in range(retries):
        status, body, headers = _request(url, token)
        if status == 200 and body is not None:
            return {it["full_name"].lower(): _record(it) for it in body.get("items", [])}
        if status in (403, 429):
            _wait_for_reset(headers)
            continue
        if status == 422:  # a repo in the batch no longer exists -> split the batch
            if len(batch) == 1:
                return {}
            mid = len(batch) // 2
            return {**_search_batch(batch[:mid], token), **_search_batch(batch[mid:], token)}
        log.warning("Search request failed (%s): %s", status, (body or {}).get("message"))
        time.sleep(2)
    return {}


def _rest_one(repo: str, token: str | None) -> dict | None:
    status, body, headers = _request(f"{API}/repos/{urllib.parse.quote(repo, safe='/')}", token)
    if status == 200 and body:
        return _record(body)
    if status in (403, 429) and "rate limit" in str((body or {}).get("message", "")).lower():
        raise RuntimeError("rate limited")
    return None


def load_cache(path: pathlib.Path) -> dict[str, dict]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_cache(path: pathlib.Path, data: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def enrich(
    repos: list[str],
    cache_file: pathlib.Path,
    token: str | None = None,
    refresh: bool = False,
    rest_fallback: bool = True,
) -> dict[str, dict]:
    """Return ``{repo: metadata}`` for every repo, fetching whatever is not cached.

    Repositories that cannot be found are cached as ``{}`` so they are not retried
    on every run (use ``refresh=True`` to retry them).
    """
    cache = {} if refresh else load_cache(cache_file)
    todo = [r for r in repos if r not in cache]
    if not todo:
        return {r: cache.get(r, {}) for r in repos}

    groups = batches(todo)
    log.info("Fetching metadata for %d repositories in %d search requests", len(todo), len(groups))
    # Authenticated search: 30 req/min. Unauthenticated: 10 req/min.
    pause = 2.1 if token else 6.2
    for i, batch in enumerate(groups, 1):
        found = _search_batch(batch, token)
        for repo in batch:
            if repo.lower() in found:
                cache[repo] = found[repo.lower()]
        if i % 10 == 0 or i == len(groups):
            save_cache(cache_file, cache)
            log.info("  metadata batch %d/%d", i, len(groups))
        time.sleep(pause)

    missing = [r for r in todo if r not in cache]
    if missing and rest_fallback:
        log.info("Resolving %d repositories via REST (renamed or deleted)", len(missing))
        for repo in missing:
            try:
                cache[repo] = _rest_one(repo, token) or {}
            except RuntimeError:
                log.warning("REST rate limit reached; remaining repositories stay unresolved")
                break
            time.sleep(0.2 if token else 1.0)
    for repo in todo:
        cache.setdefault(repo, {})
    save_cache(cache_file, cache)
    return {r: cache.get(r, {}) for r in repos}
