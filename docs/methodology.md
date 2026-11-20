# Methodology

## 1. Data

GitHub does not publish historical Trending pages. `trendwaves` reads the community archive
[antonkomarev/github-trending-archive](https://github.com/antonkomarev/github-trending-archive),
which snapshots `github.com/trending` (all languages, daily range) every day. Each snapshot is a
ranked list of `owner/name` strings. Snapshots are cached locally as-is, so a run is reproducible
offline (`--offline`).

Only the first `--top` entries (default 10) of each day are used.

## 2. Scoring

Each appearance earns points by rank:

| scheme | rank 1 | rank 2 | … | rank 10 | points per full day |
|---|---|---|---|---|---|
| `linear` (default) | 10 | 9 | … | 1 | 55 |
| `reciprocal` | 1 | 0.5 | … | 0.1 | 2.93 |
| `flat` | 1 | 1 | … | 1 | 10 |

`linear` is a compromise: the top spot matters more, but a repository at #8 still counts.
Because the daily total is fixed, a topic's points are a **share of attention on the Trending
page**, not an absolute measure of popularity.

## 3. Classification

Every repository gets one primary `(topic, subtopic)` label:

1. **Overrides**: hand-curated labels in `[overrides]` of the taxonomy file.
2. **Rules**: an ordered list of regular expressions, matched against the owner, name,
   description and GitHub topics (`-`/`_` turned into spaces, camelCase split). First match wins.
3. Otherwise **Other / Unclassified**.

Descriptions and topics are fetched from the GitHub API at run time, in batches of roughly ten
repositories per search request (`repo:a/b repo:c/d …`). Important caveat: this is the
repository's metadata **today**, not on the day it trended.

`coverage.json` records how many repositories were labelled by each method and what share of
points stayed unclassified. `repositories.csv` has a `matched_text` column showing which words
triggered each label, so mistakes are easy to audit.

## 4. Smoothing and shares

Daily points per category are smoothed with a trailing mean (`--smooth`, default 7 days).
Days missing from the archive are left empty (NaN) and skipped by the mean; they are never
counted as zero. Shares divide each category by the day's total.

## 5. Wave detection

For each topic and subtopic, using its smoothed series *s*:

```
threshold = max(3 points, mean(s) + Z · std(s))        Z = --wave-z, default 0.75
```

A **wave** is a run of consecutive days above the threshold. Runs separated by three days or
less are merged; runs shorter than `--wave-min-days` (default 5) are dropped. For each wave
`waves.csv` reports:

- `start`, `peak`, `end`, `days`
- `peak_points`, `peak_share`: height at the peak
- `baseline_points`, `lift`: the category's normal level, and peak / normal
- `wave_points`: raw points earned during the wave
- `top_repositories`, `lead_repository`: who carried it

Because the threshold is relative to each category's own history, a small subtopic can have a
wave just as clearly as a dominant one. `lift` tells you how unusual it was.

## 6. Momentum

`REPORT.md` compares each subtopic's average daily points over the last 14 days with the 56 days
before. It is a quick "what is heating up now" view, not a forecast.

## Limitations

- Trending ranks recent star velocity, so it favours new, fast-growing projects over steady ones.
- One label per repository: multi-purpose projects are assigned to their first matching rule.
- The archive is a third-party scrape; on rare days the snapshot may be missing or partial.
- Rules are English-centric; repositories described only in other languages are more likely to
  stay unclassified (they can be added to `[overrides]`).
