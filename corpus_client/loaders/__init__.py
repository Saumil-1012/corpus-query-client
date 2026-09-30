"""The list of source files the client knows about.

Supporting a new source file = write one loader module + add one line here.
"""
from __future__ import annotations

from . import catalogue, distributor, pricelist, specs

# (file name, loader module). Order only matters for display.
SOURCES = [
    ("catalogue-a.html", catalogue),
    ("catalogue-b.html", catalogue),
    ("supplier-pricelist.csv", pricelist),
    ("manufacturer-specs.json", specs),
    ("distributor-feed.xml", distributor),
]

# Which files are catalogues (they define what counts as "a product").
CATALOGUES = ["catalogue-a.html", "catalogue-b.html"]


def providers(field_name: str) -> list[str]:
    """Which source files are *able* to contain this field at all."""
    return [name for name, module in SOURCES if field_name in module.PROVIDES]
