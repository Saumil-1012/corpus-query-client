"""Reader for distributor-feed.xml (GTIN, PZN, packaging)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..models import CorpusError, Fact, SourceRecord
from .. import normalise as n

PROVIDES = {"gtin", "pzn", "package", "distributor_description"}


def _local(tag: str) -> str:
    """'{urn:...}gtin' -> 'gtin' (ignore the XML namespace)."""
    return tag.rsplit("}", 1)[-1]


def load(path: Path) -> list[SourceRecord]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise CorpusError(f"{path.name}: not valid XML ({exc})") from exc

    records = []
    for i, item in enumerate((el for el in root if _local(el.tag) == "item"), start=1):
        location = f"item {i}"
        children = {_local(c.tag): c for c in item}

        def text(name: str) -> str | None:
            el = children.get(name)
            return n.blank_to_none(el.text) if el is not None else None

        fields = {
            "gtin": Fact(text("gtin"), path.name, location, "gtin"),
            "pzn": Fact(text("pzn"), path.name, location, "pzn"),
            "distributor_description": Fact(text("description"), path.name, location, "description"),
        }
        pkg = children.get("package")
        if pkg is not None:
            level, qty, unit = pkg.get("level"), pkg.get("quantity"), pkg.get("unit")
            value = f"{level} of {qty} × {unit}" if level and qty and unit else None
            fields["package"] = Fact(value, path.name, location, "package",
                                     raw=f'level="{level}" quantity="{qty}" unit="{unit}"')
        else:
            fields["package"] = Fact(None, path.name, location, "package")

        records.append(SourceRecord(
            source=path.name,
            location=location,
            sku=n.sku(text("sellerSku")),
            model=None,
            variant=None,
            gtin=text("gtin"),
            fields=fields,
        ))
    return records
