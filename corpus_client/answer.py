"""Query -> printed answer. Deterministic: only prints values that exist in the files.

Every value is printed with the file and row it came from. Every gap is printed with the
reason: either "no file has it" or "the file has the column but the cell is empty".
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from . import normalise as n
from .index import Corpus
from .loaders import CATALOGUES, providers
from .models import Fact, Product
from .query import FIELD_LABELS, Query

SPEC_FIELDS = ["gauge", "outer_diameter_mm", "working_length_mm", "connector", "sterility",
               "geometry", "tip", "safety_mechanism", "material"]
IDENTITY_FIELDS = ["model", "variant", "raw_code", "description"]
COMMERCIAL_FIELDS = ["manufacturer", "price", "gtin", "pzn", "package"]

LABELS = {**FIELD_LABELS, "raw_code": "Catalogue code", "currency": "Currency",
          "supplier": "Supplier", "valid_from": "Valid from",
          "distributor_description": "Distributor description"}
W = 22  # label column width


def answer(corpus: Corpus, q: Query) -> str:
    if q.intent == "product_info":
        return product_info(corpus, q.sku)
    if q.intent == "field":
        return field_answer(corpus, q.sku, q.field)
    if q.intent == "by_manufacturer":
        return by_manufacturer(corpus, q.manufacturer)
    if q.intent == "count_products":
        return count_products(corpus, q.scope)
    return unsupported(q)


# ---- building blocks ----------------------------------------------------------------

def _not_found(corpus: Corpus, sku: str) -> str:
    lines = [f'No product with seller SKU "{sku}" exists in any of the {len(corpus.loaded_files)} source files.',
             f"Searched: {', '.join(corpus.loaded_files)}."]
    similar = corpus.similar_skus(sku)
    if similar:
        lines.append(f"Similar SKUs that do exist: {', '.join(similar)} (not assumed to be the same product).")
    return "\n".join(lines)


def _distinct(facts) -> list[str]:
    return list(dict.fromkeys(f.value for f in facts))


def _where_list(facts) -> str:
    return "; ".join(f.where for f in facts)


def _missing_reason(product: Product, field: str) -> str:
    """Why a field has no value for this product: empty cell, or no row in any file that could have it."""
    parts = []
    blanks = product.blanks(field)
    if blanks:
        parts.append("the cell is empty in " + _where_list(blanks))
    no_row = [src for src in providers(field) if src not in product.sources]
    if no_row:
        pretty = [
            "manufacturer-specs.json (no record with this model + variant)" if s == "manufacturer-specs.json" else s
            for s in no_row
        ]
        parts.append("no row for this SKU in " + ", ".join(pretty))
    status = "EMPTY IN SOURCE" if blanks else "NOT IN CORPUS"
    return f"{status} - " + "; ".join(parts)


def _value_line(product: Product, field: str) -> str | None:
    """'value   [source]' or a CONFLICT line; None if no value."""
    facts = product.values(field)
    if not facts:
        return None
    if field == "price":
        offers = _offers(product)
        if len(offers) == 1:
            o = offers[0]
            return f"{o.price} {o.currency or '(currency not stated)'}   [{o.fact.where}]"
        return f"{len(offers)} offers, kept separate: " + "; ".join(_offer_short(o) for o in offers)
    values = _distinct(facts)
    if len(values) == 1:
        return f"{values[0]}   [{_where_list(facts)}]"
    by_value = "; ".join(f"{v} ({_where_list([f for f in facts if f.value == v])})" for v in values)
    return f"CONFLICT - sources disagree: {by_value}. Not resolved."


@dataclass
class Offer:
    """One price together with what the SAME source row says about it."""
    fact: Fact
    price: str
    currency: str | None
    supplier: str | None
    valid_from: str | None


def _offers(product: Product) -> list[Offer]:
    """Every price, each paired only with supplier/date/currency from its own file row - never mixed."""
    def same_row(name: str, f: Fact) -> str | None:
        return next((x.value for x in product.values(name) if x.source == f.source and x.location == f.location), None)
    offers = [Offer(f, f.value, same_row("currency", f), same_row("supplier", f), same_row("valid_from", f))
              for f in product.values("price")]
    return sorted(offers, key=lambda o: (float(o.price) if o.price.replace(".", "", 1).isdigit() else 0, o.fact.source))


def _offer_short(o: Offer) -> str:
    return (f"{o.price} {o.currency or '(currency not stated)'} from {o.supplier or 'supplier not stated'}, "
            f"valid from {o.valid_from or 'not stated'} [{o.fact.where}]")


def _gtin_warnings(product: Product) -> list[str]:
    notes = []
    for gtin in _distinct(product.values("gtin")):
        ok, expected = n.gtin_check_digit_ok(gtin)
        if not ok:
            detail = f"the GS1 rule gives {expected}, the file has {gtin[-1]}" if expected is not None \
                else "it is not 8, 12, 13 or 14 digits"
            notes.append(f"GTIN {gtin} fails the GS1 check-digit test ({detail}). "
                         "Shown exactly as in the source, not corrected - treat as unverified.")
    return notes


def _price_warnings(product: Product) -> list[str]:
    if not product.values("price"):
        return []
    notes = []
    pkg = product.values("package")
    if pkg:
        notes.append(f'Unit of the price is not stated: the price list has no unit column, and '
                     f'{pkg[0].where} sells this SKU as "{pkg[0].value}". Per piece or per pack is unknown.')
    else:
        notes.append("Unit of the price is not stated in the price list (per piece or per pack is unknown), "
                     "and no packaging data exists for this SKU.")
    offers = _offers(product)
    no_supplier = [o.fact.source for o in offers if not o.supplier]
    no_date = [o.fact.source for o in offers if not o.valid_from]
    if no_supplier or no_date:
        gaps = " or ".join(x for x, missing in (("supplier", no_supplier), ("validity date", no_date)) if missing)
        notes.append(f"No {gaps} stated in {', '.join(sorted(set(no_supplier + no_date)))}, "
                     "so who offers this price and how current it is are unknown.")
    if len({o.fact.source for o in offers}) == 1:
        notes.append("Only one file contains prices, so this price cannot be cross-checked against another source.")
    else:
        notes.append("Offers from different sources are shown side by side, not merged or averaged: which one "
                     "applies depends on the supplier contract and date.")
    return notes


def _header(corpus: Corpus, product: Product) -> list[str]:
    found = [f"{s} ({loc})" for s, loc in product.sources.items()]
    absent = [s for s in corpus.loaded_files if s not in product.sources]
    lines = [f"Seller SKU {product.sku}",
             f"Found in {len(found)} of {len(corpus.loaded_files)} files: {', '.join(found)}"]
    if absent:
        lines.append(f"Not in: {', '.join(absent)}")
    return lines


# ---- intents --------------------------------------------------------------------------

def product_info(corpus: Corpus, sku: str) -> str:
    product = corpus.get(sku)
    if product is None:
        return _not_found(corpus, sku)

    lines = _header(corpus, product)
    known, unknown = [], []
    for field in IDENTITY_FIELDS + COMMERCIAL_FIELDS:
        line = _value_line(product, field)
        if line:
            known.append(f"  {LABELS[field]:<{W}}{line}")
        else:
            unknown.append(f"  {LABELS[field]:<{W}}{_missing_reason(product, field)}")

    spec_known = [f for f in SPEC_FIELDS if product.values(f)]
    for field in spec_known:
        known.append(f"  {LABELS[field]:<{W}}{_value_line(product, field)}")
    spec_unknown = [f for f in SPEC_FIELDS if not product.values(f)]
    if spec_unknown and not spec_known and not any(product.blanks(f) for f in spec_unknown):
        unknown.append(f"  {'Technical specs':<{W}}NOT IN CORPUS - no row for this SKU in "
                       "supplier-pricelist.csv or manufacturer-specs.json (no record with this model + variant)")
    else:
        for field in spec_unknown:
            unknown.append(f"  {LABELS[field]:<{W}}{_missing_reason(product, field)}")

    lines += ["", "WHAT THE CORPUS SAYS", *known]
    if unknown:
        lines += ["", "WHAT THE CORPUS DOES NOT SAY", *unknown]

    notes = product.link_notes + _gtin_warnings(product) + _price_warnings(product)
    if not product.values("manufacturer"):
        brand = (product.first("model") or "").split(" ")[0]
        if brand:
            notes.append(f'The model name starts with "{brand}". That is a brand name, not a stated manufacturer, '
                         "so no manufacturer is inferred from it.")
    if notes:
        lines += ["", "NOTES", *[f"  - {x}" for x in notes]]
    return "\n".join(lines)


def field_answer(corpus: Corpus, sku: str, field: str) -> str:
    product = corpus.get(sku)
    if product is None:
        return _not_found(corpus, sku)

    label = LABELS.get(field, field)
    facts = product.values(field)
    if not facts:
        lines = [f"{label} of {product.sku}: not available.",
                 f"  Reason: {_missing_reason(product, field)}",
                 f"  Files that can contain {label.lower()}: {', '.join(providers(field))}"]
        return "\n".join(lines)

    values = _distinct(facts)
    if field == "price":
        offers = _offers(product)
        if len(offers) == 1:
            o = offers[0]
            lines = [f"{label} of {product.sku}: {o.price} {o.currency or '(currency not stated)'}",
                     f"  Source: {o.fact.where} (column \"{o.fact.column}\")",
                     f"  Supplier: {o.supplier or 'not stated in ' + o.fact.source}",
                     f"  Valid from: {o.valid_from or 'not stated in ' + o.fact.source}"]
        else:
            lines = [f"{label} of {product.sku}: {len(offers)} offers from different sources, kept separate",
                     *[f"  - {_offer_short(o)}" for o in offers]]
    elif len(values) == 1:
        lines = [f"{label} of {product.sku}: {values[0]}"]
        if len(facts) > 1:
            lines.append(f"  {len(facts)} sources agree: {_where_list(facts)}")
        else:
            lines.append(f"  Source: {facts[0].where} (column \"{facts[0].column}\")")
        other = [s for s in providers(field) if s not in {f.source for f in facts}]
        if other:
            lines.append(f"  Not stated in: {', '.join(other)}")
    else:
        lines = [f"{label} of {product.sku}: the sources DISAGREE - no single answer.",
                 *[f"  {v}   [{_where_list([f for f in facts if f.value == v])}]" for v in values]]

    notes = list(product.link_notes if any(f.source == "manufacturer-specs.json" for f in facts) else [])
    if field == "gtin":
        notes += _gtin_warnings(product)
    if field == "price":
        notes += _price_warnings(product)
    if notes:
        lines += ["", "NOTES", *[f"  - {x}" for x in notes]]
    return "\n".join(lines)


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


def by_manufacturer(corpus: Corpus, manufacturer: str) -> str:
    stated = corpus.manufacturers()
    match = next((name for name in stated if _norm_name(name) == _norm_name(manufacturer)), None)
    sources = ", ".join(providers("manufacturer"))

    if match is None:
        lines = [f'No file states "{manufacturer}" as a manufacturer.',
                 f"Manufacturer names that do appear (only in {sources}):"]
        lines += [f"  - {name} ({len(skus)} product{'s' if len(skus) != 1 else ''})"
                  for name, skus in sorted(stated.items())]
        return "\n".join(lines)

    skus = sorted(stated[match])
    lines = [f'Products stated to be made by "{match}": {len(skus)}']
    for sku in skus:
        p = corpus.products[sku]
        facts = [f for f in p.values("manufacturer") if f.value == match]
        lines.append(f"  {sku:<14}{p.first('model') or '':<18}[{_where_list(facts)}]")

    brand = match.split(" ")[0]
    brand_only = [
        sku for sku in corpus.catalogue_products()
        if (corpus.products[sku].first("model") or "").startswith(brand + " ")
        and not corpus.products[sku].values("manufacturer")
    ]
    lines += ["", "NOT COUNTED",
              f'  {len(brand_only)} more catalogue products have "{brand}" in their model name, but no file '
              "states who makes them.",
              "  A brand name is not proof of the manufacturer, so they are listed separately, not counted:"]
    for i in range(0, len(brand_only), 6):
        lines.append("  " + ", ".join(brand_only[i:i + 6]))
    lines += ["", "WHERE THIS COMES FROM",
              f"  Manufacturer names exist only in {sources}. The two catalogues have no manufacturer column."]
    return "\n".join(lines)


def count_products(corpus: Corpus, scope: str) -> str:
    files = CATALOGUES if scope == "all" else [scope]
    per_file = {f: corpus.catalogue_skus.get(f, []) for f in files}
    distinct = list(dict.fromkeys(s for f in files for s in per_file[f]))

    lines = [f"Products in {'the catalogues' if scope == 'all' else scope}: {len(distinct)} distinct seller SKUs"]
    for f in files:
        rows, uniq = len(per_file[f]), len(set(per_file[f]))
        dup = f", {rows - uniq} duplicate rows" if rows != uniq else ", no duplicates"
        lines.append(f"  {f:<20}{rows:>4} rows{dup}")
    if scope == "all":
        overlap = set(per_file[CATALOGUES[0]]) & set(per_file[CATALOGUES[1]])
        lines.append(f"  {'in both files':<20}{len(overlap):>4}")

    families = Counter((corpus.products[s].first("model") or "?").split(" ")[0] for s in distinct)
    lines += ["", "BY MODEL FAMILY (first word of the model name)",
              "  " + ", ".join(f"{k} {v}" for k, v in sorted(families.items(), key=lambda kv: (-kv[1], kv[0])))]

    outside = [s for s in corpus.products if s not in set(corpus.catalogue_products())]
    lines += ["", "ASSUMPTIONS AND CAVEATS"]
    if scope == "all":
        lines.append('  - "The catalogue" is read as both catalogue files together: they list different products, '
                     "so neither alone is the full catalogue.")
    lines.append("  - A product = one distinct seller SKU in a catalogue. Price list, specs and distributor feed "
                 f"are not counted separately; {len(outside)} SKUs appear in them without a catalogue row.")
    if scope in ("all", "catalogue-a.html"):
        a_skus = corpus.catalogue_skus.get("catalogue-a.html", [])
        lines.append(f"  - catalogue-a.html uses a shorter SKU format (e.g. {a_skus[0] if a_skus else '?'}, "
                     "no trailing letter); none of its products appear in any other file.")
    return "\n".join(lines)


def unsupported(q: Query) -> str:
    return "\n".join([
        "I can't answer this question from the corpus with this client.",
        f"  Reason: {q.note or 'not one of the supported question types'}.",
        "  Supported: information on a seller SKU; one attribute of a SKU (price, GTIN, PZN, packaging,",
        "  manufacturer, a technical spec); products made by a manufacturer; number of products.",
    ])
