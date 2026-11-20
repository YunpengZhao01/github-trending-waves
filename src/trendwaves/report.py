"""Markdown summary report (REPORT.md) written next to the charts and tables."""
from __future__ import annotations

import pathlib

import pandas as pd


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.0f}" if v.is_integer() else f"{v:g}"
    return str(v)


def _md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_none_\n"
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for _, row in df.iterrows():
        cells = [_fmt(v).replace("|", "\\|") for v in row.tolist()]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _repo_link(name: str) -> str:
    return f"[{name}](https://github.com/{name})" if name else ""


def write(
    out: pathlib.Path,
    coverage: dict,
    topic_share_total: pd.Series,
    repos: pd.DataFrame,
    topic_waves: pd.DataFrame,
    sub_waves: pd.DataFrame,
    momentum: pd.DataFrame,
) -> pathlib.Path:
    lines: list[str] = []
    a = lines.append
    a(f"# GitHub Trending topic waves: {coverage['start']} to {coverage['end']}\n")
    a(
        f"Top {coverage['top_n']} of the daily *All languages* Trending page, scored with the "
        f"`{coverage['scoring']}` scheme and smoothed over {coverage['smooth_days']} days. "
        f"{coverage['found_dates']} of {coverage['requested_dates']} days were available in the archive; "
        f"{coverage['unique_repositories']} distinct repositories appeared.\n"
    )
    a("![Topic heat](topic_panels.png)\n")

    a("## Where the attention went\n")
    if (out / "lead_topic_mix.png").exists():
        a("![Inside the leading topic](lead_topic_mix.png)\n")
    share = (topic_share_total * 100).round(1).rename("share of all points (%)").reset_index()
    share.columns = ["topic", "share of all points (%)"]
    a(_md_table(share))

    a("\n## Rising and cooling right now\n")
    a(f"Average daily points over the last {coverage['momentum_recent_days']} days compared with the "
      f"{coverage['momentum_prior_days']} days before that (subtopics).\n")
    if not momentum.empty:
        m = momentum.copy()
        m.columns = ["subtopic", "last 14 days (pts/day)", "previous 56 days (pts/day)", "change"]
        hot = m.head(5)
        cold = m.tail(5).iloc[::-1]
        a("**Rising**\n")
        a(_md_table(hot))
        a("\n**Cooling**\n")
        a(_md_table(cold))

    a("\n## Biggest subtopic waves\n")
    a("![Wave timeline](wave_timeline.png)\n")
    if not sub_waves.empty:
        top = sub_waves.sort_values("wave_points", ascending=False).head(15).copy()
        top["lead"] = top["lead_repository"].map(_repo_link)
        top = top[["category", "start", "peak", "end", "days", "lift", "wave_points", "lead"]]
        top.columns = ["subtopic", "start", "peak", "end", "days", "lift ×", "points", "led by"]
        a(_md_table(top))

    a("\n## Topic waves\n")
    if not topic_waves.empty:
        t = topic_waves[["category", "start", "peak", "end", "days", "lift", "wave_points", "lead_repository"]].copy()
        t["lead_repository"] = t["lead_repository"].map(_repo_link)
        t.columns = ["topic", "start", "peak", "end", "days", "lift ×", "points", "led by"]
        a(_md_table(t))

    a("\n![Subtopic heatmap](subtopic_heatmap.png)\n")

    a("\n## Most persistent repositories\n")
    r = repos.head(20).reset_index()[["repository", "subtopic", "total_points", "days_in_top", "best_rank"]].copy()
    r["repository"] = r["repository"].map(_repo_link)
    a(_md_table(r))

    a("\n## Data quality\n")
    a(f"- Missing archive days: {len(coverage['missing_dates'])}; request errors: {len(coverage['request_errors'])}")
    a(f"- Repositories with GitHub metadata: {coverage['repositories_with_metadata']} / {coverage['unique_repositories']}")
    a(f"- Unclassified: {coverage['unclassified_repositories']} repositories "
      f"({coverage['unclassified_point_share'] * 100:.1f}% of points)")
    a("- Labels come from each repository's *current* description and topics, not from the day it trended.")
    path = out / "REPORT.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
