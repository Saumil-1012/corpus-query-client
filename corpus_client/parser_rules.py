
from __future__ import annotations

import re

from .query import Query

SKU_RE = re.compile(r"\bSYN-\d{3}-\d{2}[A-Z]?\b", re.IGNORECASE)
MANUFACTURER_RE = re.compile(r"(?:made|manufactured|produced) by\s+(.+?)[\s?.!]*$", re.IGNORECASE)

FIELD_WORDS = [
    ("price", ("price", "preis", "cost")),
    ("gtin", ("gtin", "ean", "barcode")),
    ("pzn", ("pzn",)),
    ("package", ("packag", "pack size", "box")),
    ("manufacturer", ("manufacturer", "who makes", "hersteller")),
]

NAME = "keyword rules"


def parse(question: str) -> Query:
    text = question.strip()
    lower = text.lower()
    sku_match = SKU_RE.search(text)
    sku = sku_match.group(0).upper() if sku_match else None

    m = MANUFACTURER_RE.search(text)
    if m:
        return Query("by_manufacturer", manufacturer=m.group(1).strip(), parsed_by=NAME)

    if re.search(r"\bhow many\b", lower) and "product" in lower:
        scope = "all"
        for name in ("catalogue-a.html", "catalogue-b.html"):
            if name in lower:
                scope = name
        return Query("count_products", scope=scope, parsed_by=NAME)

    if sku:
        for field, words in FIELD_WORDS:
            if any(w in lower for w in words):
                return Query("field", sku=sku, field=field, parsed_by=NAME)
        return Query("product_info", sku=sku, parsed_by=NAME)

    return Query("unsupported", note="no rule matches this phrasing", parsed_by=NAME)
