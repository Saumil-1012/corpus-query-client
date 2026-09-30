"""Reader for manufacturer-specs.json. Note: this file has NO seller SKU."""
from __future__ import annotations

import json
from pathlib import Path

from ..models import CorpusError, Fact, SourceRecord
from .. import normalise as n

PROVIDES = {
    "manufacturer", "model", "variant", "gauge", "outer_diameter_mm", "working_length_mm",
    "geometry", "tip", "connector", "sterility", "safety_mechanism", "material", "gtin",
}

KEYS = {
    "manufacturer": ("manufacturer", n.blank_to_none),
    "model": ("model", n.blank_to_none),
    "variant": ("variant", n.blank_to_none),
    "nominal_gauge": ("gauge", n.number),
    "outer_diameter_mm": ("outer_diameter_mm", n.number),
    "working_length_mm": ("working_length_mm", n.number),
    "geometry": ("geometry", n.blank_to_none),
    "tip": ("tip", n.blank_to_none),
    "connector": ("connector", n.connector),
    "sterility": ("sterility", n.sterility),
    "safety_mechanism": ("safety_mechanism", n.blank_to_none),
    "material": ("material", n.blank_to_none),
    "gtin": ("gtin", n.blank_to_none),
}


def load(path: Path) -> list[SourceRecord]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise CorpusError(f"{path.name}: expected a JSON array")

    records = []
    for i, item in enumerate(data, start=1):
        location = f"record {i}"
        fields = {}
        for key, (name, normalise) in KEYS.items():
            if key not in item:
                continue
            raw = item[key]
            raw_text = None if raw is None else str(raw)
            value = normalise(raw_text)
            fields[name] = Fact(value, path.name, location, key,
                                raw=raw_text if raw_text != value else None)
        records.append(SourceRecord(
            source=path.name,
            location=location,
            sku=None,
            model=n.blank_to_none(item.get("model")),
            variant=n.blank_to_none(item.get("variant")),
            gtin=n.blank_to_none(item.get("gtin")),
            fields=fields,
        ))
    return records
