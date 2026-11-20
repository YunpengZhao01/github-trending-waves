# Contributing

Thanks for helping! The most useful contributions are usually **better labels**.

## Improve the taxonomy

1. Look at `results/repositories.csv` and sort by `total_points`. Rows with
   `classification_method = unclassified`, or with an obviously wrong `subtopic`, are the ones to fix.
2. Check why a repository got its label:

   ```bash
   trendwaves classify owner/name
   # owner/name: AI & ML / MCP & tool use [metadata]  (matched "mcp server")
   ```

3. Edit `src/trendwaves/default_taxonomy.toml`:
   - add a pattern to an existing `[[rule]]` (rules are tried top to bottom, first match wins), or
   - add the repository under `[overrides]` when its description is misleading.
4. Re-run `trendwaves run --offline` and check that the unclassified share in `results/coverage.json` went down.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest -q
```

Please keep pull requests focused, and add a test when you change scoring, wave detection or classification logic.
