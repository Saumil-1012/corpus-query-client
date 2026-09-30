"""Reader for supplier-pricelist.csv (semicolon-separated, German headers)."""
from __future__ import annotations

import csv
from pathlib import Path

from ..models import CorpusError, Fact, SourceRecord
from .. import normalise as n

PROVIDES = {
    "manufacturer", "model", "gauge", "outer_diameter_mm", "working_length_mm",
    "connector", "sterility", "price", "currency",
}

# German column header -> (our field name, normaliser)
COLUMNS = {
    "Artikelnummer": ("sku", n.sku),
    "Hersteller": ("manufacturer", n.blank_to_none),
    "Modellname": ("model", n.blank_to_none),
    "Groesse (G)": ("gauge", n.number),
    "Aussendurchmesser [mm]": ("outer_diameter_mm", n.number),
    "Arbeitslaenge [mm]": ("working_length_mm", n.number),
    "Anschluss": ("connector", n.connector),
    "Steril": ("sterility", n.sterility),
    "Preis EUR": ("price", n.price),
    "Waehrung": ("currency", n.blank_to_none),
    # Optional: not in today's file, read if a future version of the price list has them.
    "Lieferant": ("supplier", n.blank_to_none),
    "Gueltig ab": ("valid_from", n.blank_to_none),
}


def load(path: Path) -> list[SourceRecord]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        missing = [c for c in ("Artikelnummer", "Preis EUR") if c not in (reader.fieldnames or [])]
        if missing:
            raise CorpusError(f"{path.name}: expected columns {missing} not found in header {reader.fieldnames}")

        records = []
        # line 1 is the header, so the first data row is line 2
        for line_no, row in enumerate(reader, start=2):
            location = f"line {line_no}"
            fields: dict[str, Fact] = {}
            for col, (name, normalise) in COLUMNS.items():
                if name == "sku" or col not in row:
                    continue
                raw = row[col]
                value = normalise(raw)
                fields[name] = Fact(value, path.name, location, col,
                                    raw=raw if raw != value else None)
            records.append(SourceRecord(
                source=path.name,
                location=location,
                sku=n.sku(row["Artikelnummer"]),
                model=n.blank_to_none(row.get("Modellname")),
                variant=None,  # the price list has no variant column
                gtin=None,
                fields=fields,
            ))
    return records
