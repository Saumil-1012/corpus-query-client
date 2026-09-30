"""Reader for the two HTML seller catalogues (catalogue-a.html, catalogue-b.html)."""
from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from ..models import CorpusError, Fact, SourceRecord
from .. import normalise as n

PROVIDES = {"model", "variant", "raw_code", "description"}

COLUMNS = {
    "Raw catalogue code": "raw_code",
    "Product model": "model",
    "Variant": "variant",
    "Seller SKU": "sku",
    "Description": "description",
}


def load(path: Path) -> list[SourceRecord]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    table = soup.find("table")
    if table is None:
        raise CorpusError(f"{path.name}: no <table> found")

    headers = [th.get_text(strip=True) for th in table.select("thead th")]
    unknown = [h for h in headers if h not in COLUMNS]
    if unknown or "Seller SKU" not in headers:
        raise CorpusError(f"{path.name}: unexpected table columns {headers}")

    records = []
    for i, tr in enumerate(table.select("tbody tr"), start=1):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) != len(headers):
            raise CorpusError(f"{path.name}: table row {i} has {len(cells)} cells, expected {len(headers)}")
        row = dict(zip(headers, cells))
        location = f"table row {i}"
        fields = {
            COLUMNS[col]: Fact(n.blank_to_none(val), path.name, location, col)
            for col, val in row.items()
            if COLUMNS[col] != "sku"
        }
        records.append(SourceRecord(
            source=path.name,
            location=location,
            sku=n.sku(row["Seller SKU"]),
            model=n.blank_to_none(row.get("Product model")),
            variant=n.blank_to_none(row.get("Variant")),
            gtin=None,
            fields=fields,
        ))
    return records
