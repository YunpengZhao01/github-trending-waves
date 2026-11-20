import datetime as dt
import json

from trendwaves.cli import main


def test_end_to_end_offline(tmp_path):
    cache = tmp_path / "cache"
    (cache / "daily").mkdir(parents=True)
    start = dt.date(2026, 1, 1)
    pool = ["acme/mcp-server", "acme/pentest", "acme/react-ui", "acme/llm-chat", "acme/game-engine",
            "acme/docker-tool", "acme/awesome-list", "acme/crypto-bot", "acme/notes-app", "acme/thing",
            "acme/rag-kit", "acme/vim-plugin"]
    for i in range(60):
        day = start + dt.timedelta(days=i)
        lst = pool[i % 3:] + pool[: i % 3]
        if 20 <= i < 35:  # make MCP surge
            lst = ["acme/mcp-server"] + [r for r in lst if r != "acme/mcp-server"]
        (cache / "daily" / f"{day}.json").write_text(json.dumps({"date": str(day), "list": lst}))
    out = tmp_path / "out"
    rc = main(["run", "--offline", "--no-metadata", "--cache", str(cache), "--out", str(out),
               "--start", "2026-01-01", "--end", "2026-03-02"])
    assert rc == 0
    for f in ("daily_top.csv", "repositories.csv", "waves.csv", "coverage.json", "REPORT.md", "topic_panels.png",
              "topic_streamgraph.png", "subtopic_heatmap.png"):
        assert (out / f).exists(), f
    cov = json.loads((out / "coverage.json").read_text())
    assert cov["found_dates"] == 60 and len(cov["missing_dates"]) == 1  # 2026-03-01 not cached
