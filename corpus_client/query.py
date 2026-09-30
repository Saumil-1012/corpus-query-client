
from __future__ import annotations

from dataclasses import dataclass

INTENTS = ("product_info", "field", "by_manufacturer", "count_products", "unsupported")

# Fields a user can ask for with intent="field". Keys are our internal names.
FIELD_LABELS = {
    "price": "Price",
    "gtin": "GTIN",
    "pzn": "PZN",
    "package": "Packaging",
    "manufacturer": "Manufacturer",
    "model": "Product model",
    "variant": "Variant",
    "description": "Description",
    "gauge": "Gauge (G)",
    "outer_diameter_mm": "Outer diameter (mm)",
    "working_length_mm": "Working length (mm)",
    "connector": "Connector",
    "sterility": "Sterility",
    "geometry": "Geometry",
    "tip": "Tip",
    "safety_mechanism": "Safety mechanism",
    "material": "Material",
}

SCOPES = ("all", "catalogue-a.html", "catalogue-b.html")


@dataclass
class Query:
    intent: str
    sku: str | None = None
    field: str | None = None
    manufacturer: str | None = None
    scope: str = "all"
    note: str | None = None      # parser's reason when intent == "unsupported"
    parsed_by: str = ""

    def describe(self) -> str:
        if self.intent == "product_info":
            what = f"all information on seller SKU {self.sku}"
        elif self.intent == "field":
            what = f"{FIELD_LABELS.get(self.field or '', self.field)} of seller SKU {self.sku}"
        elif self.intent == "by_manufacturer":
            what = f'products made by "{self.manufacturer}"'
        elif self.intent == "count_products":
            what = "number of products" + ("" if self.scope == "all" else f" in {self.scope}")
        else:
            what = "a question this client cannot answer"
        return f"Understood as: {what}   [parsed by {self.parsed_by}]"
