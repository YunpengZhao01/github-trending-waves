"""Command-line interface: ``trendwaves run`` / ``trendwaves fetch`` / ``trendwaves classify``."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import pathlib
import sys

import pandas as pd

from . import __version__, archive, metadata, plotting, report, scoring, waves
from .taxonomy import Taxonomy

log = logging.getLogger("trendwaves")


def _date(s: str) -> dt.date:
    if s == "today":
        return dt.date.today()
    try:
        return dt.date.fromisoformat(s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {s!r}") from exc


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--start", type=_date, default=_date("2026-01-01"), help="first day, YYYY-MM-DD (default 2026-01-01)")
    p.add_argument("--end", type=_date, default=dt.date.today() - dt.timedelta(days=1),
                   help="last day, YYYY-MM-DD or 'today' (default: yesterday)")
    p.add_argument("--cache", type=pathlib.Path, default=pathlib.Path(".trendwaves-cache"),
                   help="cache directory for archive snapshots and metadata (default .trendwaves-cache)")
    p.add_argument("--offline", action="store_true", help="use cached data only; never touch the network")
    p.add_argument("--refresh", action="store_true", help="re-download cached archive days and metadata")
    p.add_argument("-v", "--verbose", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="trendwaves",
        description="Score the daily GitHub Trending top-N and watch topics rise and fall in waves.",
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="fetch, classify, score, detect waves and draw charts")
    _common(run)
    run.add_argument("--out", type=pathlib.Path, default=pathlib.Path("results"), help="output directory (default results)")
    run.add_argument("--top", type=int, default=10, help="how many repositories per day to score (default 10)")
    run.add_argument("--scoring", choices=sorted(scoring.SCHEMES), default="linear",
                     help="points per rank: linear (N..1, default), reciprocal (1/rank) or flat")
    run.add_argument("--smooth", type=int, default=7, help="trailing moving-average window in days (default 7)")
    run.add_argument("--taxonomy", type=pathlib.Path, help="custom taxonomy TOML (default: built-in)")
    run.add_argument("--no-metadata", action="store_true", help="classify from repository names only")
    run.add_argument("--wave-z", type=float, default=0.75, help="wave threshold = mean + Z*std (default 0.75)")
    run.add_argument("--wave-min-days", type=int, default=5, help="shortest wave kept, in days (default 5)")
    run.add_argument("--no-charts", action="store_true", help="skip PNG charts")

    fetch = sub.add_parser("fetch", help="only download archive snapshots (and metadata) into the cache")
    _common(fetch)
    fetch.add_argument("--top", type=int, default=10)
    fetch.add_argument("--no-metadata", action="store_true")

    cls = sub.add_parser("classify", help="print the label a repository would get (for tuning a taxonomy)")
    cls.add_argument("repos", nargs="+", help="owner/name ...")
    cls.add_argument("--taxonomy", type=pathlib.Path)
    cls.add_argument("--cache", type=pathlib.Path, default=pathlib.Path(".trendwaves-cache"))
    return ap


def _token() -> str | None:
    return os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or None


def _load(args) -> tuple[archive.ArchiveResult, dict[str, dict], list[str]]:
    if args.end < args.start:
        raise SystemExit("error: --end is before --start")
    res = archive.fetch(args.start, args.end, args.cache / "daily", refresh=args.refresh, offline=args.offline)
    if not res.days:
        raise SystemExit("error: no archive data could be loaded (check the date range and your connection)")
    repos: dict[str, None] = {}
    for lst in res.days.values():
        for r in lst[: args.top]:
            repos.setdefault(r, None)
    names = list(repos)
    meta_file = args.cache / "github_metadata.json"
    if args.no_metadata:
        meta: dict[str, dict] = {}
    elif args.offline:
        cached = metadata.load_cache(meta_file)
        meta = {r: cached.get(r, {}) for r in names}
    else:
        if not _token():
            log.warning("No GITHUB_TOKEN set: metadata requests are rate limited to 10/min (still works, just slower).")
        meta = metadata.enrich(names, meta_file, token=_token(), refresh=args.refresh)
    return res, meta, names


def cmd_fetch(args) -> int:
    res, meta, names = _load(args)
    print(f"cached {len(res.days)} days, {len(names)} repositories, {sum(bool(v) for v in meta.values())} with metadata")
    return 0


def cmd_classify(args) -> int:
    tax = Taxonomy.load(args.taxonomy)
    cached = metadata.load_cache(args.cache / "github_metadata.json")
    for repo in args.repos:
        lab = tax.classify(repo, cached.get(repo))
        extra = f'  (matched "{lab.matched}")' if lab.matched else ""
        print(f"{repo}: {lab.topic} / {lab.subtopic} [{lab.method}]{extra}")
    return 0


def cmd_run(args) -> int:
    if args.smooth < 1 or args.top < 1:
        raise SystemExit("error: --smooth and --top must be >= 1")
    tax = Taxonomy.load(args.taxonomy)
    res, meta, names = _load(args)
    out: pathlib.Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    labels = {r: tax.classify(r, meta.get(r)) for r in names}
    table = scoring.attach_labels(scoring.rank_table(res.days, args.top, args.scoring), labels)
    all_days = list(archive.daterange(args.start, args.end))

    topics_raw = scoring.daily_matrix(table, "topic", all_days)
    subs_raw = scoring.daily_matrix(table, "subtopic", all_days)
    topics_s, subs_s = scoring.smooth(topics_raw, args.smooth), scoring.smooth(subs_raw, args.smooth)
    topics_share, subs_share = scoring.share(topics_s), scoring.share(subs_s)

    kw = dict(z=args.wave_z, min_days=args.wave_min_days)
    tw = waves.to_frame(waves.detect(topics_s, topics_share, table, "topic", "topic", **kw))
    sw = waves.to_frame(waves.detect(subs_s, subs_share, table, "subtopic", "subtopic", **kw))
    mom = waves.momentum(subs_raw.drop(columns=["Unclassified"], errors="ignore"))
    repos = scoring.repository_summary(table, labels, meta)

    # ---------------------------------------------------------------- tables
    t = table.copy()
    t["date"] = t["date"].dt.date
    t.to_csv(out / "daily_top.csv", index=False)
    repos.to_csv(out / "repositories.csv")
    for name, raw, sm, sh in (("topic", topics_raw, topics_s, topics_share), ("subtopic", subs_raw, subs_s, subs_share)):
        long = (
            raw.stack(future_stack=True).rename("raw_points").to_frame()
            .join(sm.stack(future_stack=True).rename(f"smoothed_{args.smooth}d"))
            .join(sh.stack(future_stack=True).rename("share"))
            .dropna(subset=["raw_points"]).round(5).reset_index()
        )
        long.columns = ["date", name, *long.columns[2:]]
        long["date"] = long["date"].dt.date
        long.to_csv(out / f"daily_{name}_scores.csv", index=False)
    pd_waves = pd.concat([tw, sw], ignore_index=True)
    pd_waves.to_csv(out / "waves.csv", index=False)

    # -------------------------------------------------------------- coverage
    pts = table.groupby("classification_method")["points"].sum()
    coverage = {
        "trendwaves_version": __version__,
        "source": archive.SOURCE_REPO,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "start": str(args.start), "end": str(args.end), "top_n": args.top, "scoring": args.scoring,
        "smooth_days": args.smooth, "wave_z": args.wave_z, "wave_min_days": args.wave_min_days,
        "momentum_recent_days": 14, "momentum_prior_days": 56,
        "requested_dates": len(all_days), "found_dates": len(res.days),
        "missing_dates": [str(d) for d in res.missing],
        "request_errors": {str(k): v for k, v in res.errors.items()},
        "ranking_records": int(len(table)), "unique_repositories": len(names),
        "repositories_with_metadata": sum(bool(meta.get(r)) for r in names),
        "classification_methods": {m: sum(lab.method == m for lab in labels.values())
                                   for m in ("override", "metadata", "name_only", "unclassified")},
        "unclassified_repositories": sum(lab.method == "unclassified" for lab in labels.values()),
        "unclassified_point_share": round(float(pts.get("unclassified", 0) / pts.sum()), 4),
        "waves_detected": {"topic": int(len(tw)), "subtopic": int(len(sw))},
        "caution": "Labels use each repository's current GitHub metadata, not a point-in-time snapshot.",
    }
    (out / "coverage.json").write_text(json.dumps(coverage, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---------------------------------------------------------------- charts
    if not args.no_charts:
        topic_order = list(topics_raw.columns)
        colors = plotting.colors_for([c for c in tax.topics if c in topic_order] + ["Other"])
        topic_of = {s: tax.topic_of(s) for s in subs_raw.columns}
        footer = (f"Data: {archive.SOURCE_REPO} · top {args.top} per day, {args.scoring} rank points · "
                  f"labels are rule-based (trendwaves {__version__})")
        valid = topics_share.dropna(how="all")
        ordered = valid[[c for c in colors if c in valid.columns]]
        plotting.topic_panels(ordered, tw, colors, out / "topic_panels.png", footer, args.smooth)
        # what *kind* of work drove the dominant topic
        lead = ordered.drop(columns=["Other"], errors="ignore").mean().idxmax()
        lead_subs = [s for s in subs_raw.columns if topic_of.get(s) == lead]
        if len(lead_subs) > 1:
            inner = subs_raw[lead_subs].dropna(how="all")
            inner = inner[inner.sum().sort_values(ascending=False).index]
            if inner.shape[1] > 8:  # fold the tail into one grey band, never invent a 9th hue
                keep = list(inner.columns[:7])
                inner = inner[keep].assign(**{"Everything else": inner.drop(columns=keep).sum(axis=1)})
            inner_share = scoring.share(scoring.smooth(inner, max(args.smooth, 14)))
            sub_colors = plotting.colors_for([c for c in inner_share.columns if c != "Everything else"])
            sub_colors["Everything else"] = plotting.OTHER
            plotting.subtopic_share_area(
                inner_share, sub_colors, out / "lead_topic_mix.png", footer,
                f"Inside {lead}: what kind of project was trending",
                f"Share of {lead} points by subtopic ({max(args.smooth, 14)}-day mean, stacked to 100%)")
        plotting.streamgraph(ordered, colors, out / "topic_streamgraph.png", footer, args.smooth)
        plotting.subtopic_heatmap(subs_raw.dropna(how="all"), topic_of, out / "subtopic_heatmap.png", footer)
        plotting.wave_timeline(sw, topic_of, colors, out / "wave_timeline.png", footer)

    report.write(out, coverage, topics_raw.sum() / topics_raw.sum().sum(), repos, tw, sw, mom)
    print(f"Done: {len(res.days)} days, {len(names)} repositories, {len(tw)} topic waves, "
          f"{len(sw)} subtopic waves -> {out}/REPORT.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING,
                        format="%(levelname)s %(message)s")
    return {"run": cmd_run, "fetch": cmd_fetch, "classify": cmd_classify}[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
