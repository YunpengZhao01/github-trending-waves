# Changelog

## 0.1.0 (2026-11-19)

First public release.

- `trendwaves run`: fetch the daily GitHub Trending archive, score the top N, classify repositories, detect topic waves, write CSVs, charts and a Markdown report.
- `trendwaves fetch` and `trendwaves classify` helper commands.
- Batched metadata lookup through the GitHub search API (about 10 repositories per request) with a REST fallback.
- Editable TOML taxonomy with per-repository overrides.
- Three scoring schemes: `linear`, `reciprocal`, `flat`.
- Charts: topic share lines, streamgraph, subtopic heatmap, wave timeline.
- Daily GitHub Actions workflow that keeps `results/` up to date.
