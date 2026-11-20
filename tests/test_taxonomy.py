import pytest

from trendwaves.taxonomy import Taxonomy


@pytest.fixture(scope="module")
def tax():
    return Taxonomy.load()


def test_default_taxonomy_loads(tax):
    assert len(tax.rules) > 10
    assert "AI & ML" in tax.topics


def test_override_wins(tax):
    label = tax.classify("astral-sh/uv", {"description": "An extremely fast Python package manager"})
    assert (label.topic, label.subtopic, label.method) == ("Developer tools", "Package & build tools", "override")


def test_override_is_case_insensitive(tax):
    assert tax.classify("OpenAI/Codex", None).method == "override"


@pytest.mark.parametrize(
    "repo, meta, expected",
    [
        ("acme/mcp-hub", {"description": "A registry of MCP servers"}, "MCP & tool use"),
        ("acme/pentest-kit", {"description": "Penetration testing toolkit"}, "Offensive security"),
        ("acme/svelte-ui", {"description": "Component library", "topics": ["svelte"]}, "Frontend & UI"),
        ("acme/rag-engine", {"description": "Retrieval-augmented generation engine"}, "RAG & knowledge"),
    ],
)
def test_rules(tax, repo, meta, expected):
    assert tax.classify(repo, meta).subtopic == expected


def test_metadata_vs_name_only(tax):
    assert tax.classify("acme/llm-router", None).method == "name_only"
    assert tax.classify("acme/llm-router", {"description": "x"}).method == "metadata"


def test_unclassified(tax):
    label = tax.classify("acme/zzzz", {"description": "qwerty"})
    assert label.method == "unclassified" and label.topic == "Other"


def test_camel_case_split():
    assert "spoti flac" in Taxonomy.text_for("afkarxyz/SpotiFLAC", None)


def test_custom_taxonomy(tmp_path):
    p = tmp_path / "t.toml"
    p.write_text("[overrides]\n\"a/b\" = \"X / Y\"\n[[rule]]\ntopic='T'\nsubtopic='S'\npattern='\\bfoo\\b'\n")
    tax = Taxonomy.load(p)
    assert tax.classify("a/b", None).subtopic == "Y"
    assert tax.classify("c/foo", None).subtopic == "S"


def test_bad_override_rejected():
    with pytest.raises(ValueError):
        Taxonomy.from_dict({"overrides": {"a/b": "no separator"}})
