"""Small data classes shared by every part of the client.

The central idea: every value we ever print is a `Fact` that remembers which file
and which row it came from. Nothing is printed that does not have a `Fact` behind it.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class CorpusError(Exception):
    """A source file is missing or not in the shape we expect."""


class ConfigError(Exception):
    """Something the user has to set up (API key, data folder)."""


@dataclass(frozen=True)
class Fact:
    """One value from one cell of one source file."""

    value: str | None  # normalised value; None means "the cell exists but is blank"
    source: str        # file name, e.g. "supplier-pricelist.csv"
    location: str      # human-readable position, e.g. "line 3" or "table row 24"
    column: str        # the column/key as written in the source file
    raw: str | None = None  # the value exactly as written, if it differs from `value`

    @property
    def where(self) -> str:
        return f"{self.source}, {self.location}"

    @property
    def is_blank(self) -> bool:
        return self.value is None or self.value == ""


@dataclass
class SourceRecord:
    """One row/record of one source file, after reading but before joining."""

    source: str
    location: str
    sku: str | None
    model: str | None
    variant: str | None
    gtin: str | None
    fields: dict[str, Fact]


@dataclass
class Product:
    """Everything the corpus says about one seller SKU, across all files."""

    sku: str
    facts: dict[str, list[Fact]] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)  # file -> location of its row
    link_notes: list[str] = field(default_factory=list)   # how non-SKU records were attached

    def add(self, name: str, fact: Fact) -> None:
        self.facts.setdefault(name, []).append(fact)

    def values(self, name: str) -> list[Fact]:
        return [f for f in self.facts.get(name, []) if not f.is_blank]

    def blanks(self, name: str) -> list[Fact]:
        return [f for f in self.facts.get(name, []) if f.is_blank]

    def first(self, name: str) -> str | None:
        vals = self.values(name)
        return vals[0].value if vals else None
