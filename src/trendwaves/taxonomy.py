"""Rule-based topic classification driven by a TOML taxonomy file."""
from __future__ import annotations

import importlib.resources
import pathlib
import re
import sys
from dataclasses import dataclass

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

UNCLASSIFIED = ("Other", "Unclassified")


@dataclass(frozen=True)
class Rule:
    topic: str
    subtopic: str
    regex: re.Pattern


@dataclass(frozen=True)
class Label:
    topic: str
    subtopic: str
    method: str  # override | metadata | name_only | unclassified
    matched: str = ""  # the text fragment that triggered the rule


class Taxonomy:
    def __init__(self, rules: list[Rule], overrides: dict[str, tuple[str, str]]):
        self.rules = rules
        self.overrides = overrides

    # ------------------------------------------------------------------ io
    @classmethod
    def from_dict(cls, data: dict) -> Taxonomy:
        rules = []
        for i, r in enumerate(data.get("rule", [])):
            try:
                rules.append(Rule(r["topic"], r["subtopic"], re.compile(r["pattern"], re.IGNORECASE)))
            except (KeyError, re.error) as exc:
                raise ValueError(f"invalid taxonomy rule #{i + 1}: {exc}") from exc
        overrides = {}
        for repo, label in data.get("overrides", {}).items():
            if " / " not in label:
                raise ValueError(f"override for {repo!r} must look like 'Topic / Subtopic'")
            topic, sub = (s.strip() for s in label.split(" / ", 1))
            overrides[repo.lower()] = (topic, sub)
        return cls(rules, overrides)

    @classmethod
    def load(cls, path: str | pathlib.Path | None = None) -> Taxonomy:
        if path is None:
            text = importlib.resources.files("trendwaves").joinpath("default_taxonomy.toml").read_text("utf-8")
        else:
            text = pathlib.Path(path).read_text(encoding="utf-8")
        return cls.from_dict(tomllib.loads(text))

    # ------------------------------------------------------------- helpers
    @property
    def topics(self) -> list[str]:
        seen: dict[str, None] = {}
        for r in self.rules:
            seen.setdefault(r.topic, None)
        return list(seen)

    def topic_of(self, subtopic: str) -> str:
        for r in self.rules:
            if r.subtopic == subtopic:
                return r.topic
        for t, s in self.overrides.values():
            if s == subtopic:
                return t
        return UNCLASSIFIED[0]

    @staticmethod
    def _normalise(text: str) -> str:
        text = re.sub(r"[-_]+", " ", text)
        # split camelCase names: "SpotiFLAC" -> "Spoti FLAC", "vibeKanban" -> "vibe Kanban"
        text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
        return text.lower()

    @classmethod
    def text_for(cls, repo: str, meta: dict | None, include_topics: bool = True) -> str:
        meta = meta or {}
        owner, _, name = repo.partition("/")
        parts = [owner, name, meta.get("description") or ""]
        if include_topics:
            parts.append(" ".join(meta.get("topics") or []))
        return cls._normalise(" ".join(parts))

    def classify(self, repo: str, meta: dict | None) -> Label:
        """Overrides first; then rules on name + description; then rules again with GitHub topics added.

        The two passes keep a repository's own words in charge: a generic topic tag such as
        ``mcp`` or ``react`` only decides the label when the description says nothing useful.
        """
        key = repo.lower()
        if key in self.overrides:
            return Label(*self.overrides[key], "override")
        method = "metadata" if meta else "name_only"
        for include_topics in (False, True):
            text = self.text_for(repo, meta, include_topics=include_topics)
            for rule in self.rules:
                m = rule.regex.search(text)
                if m:
                    matched = m.group(0).strip()
                    if len(matched) > 40:
                        matched = matched[:37] + "..."
                    return Label(rule.topic, rule.subtopic, method, matched)
        return Label(*UNCLASSIFIED, "unclassified")
