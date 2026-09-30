"""Joins the five files into one view per seller SKU, keeping every value's origin.

Join rules (in this order, nothing fuzzy):
1. Records that carry a seller SKU (catalogues, price list, distributor feed) are attached
   to that SKU exactly.
2. manufacturer-specs.json has no SKU. A spec record is attached to a product only if a
   catalogue row has exactly the same model name AND variant ("RecallSafe 142" + "21 T").
   If that fails, we try an exact GTIN match against the distributor feed.
   If both fail, the record stays "unlinked" and is reported, never guessed.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from . import loaders
from .loaders import CATALOGUES
from .models import ConfigError, Product, SourceRecord


@dataclass
class Corpus:
    products: dict[str, Product] = field(default_factory=dict)
    catalogue_skus: dict[str, list[str]] = field(default_factory=dict)  # file -> SKUs, in file order
    unlinked: list[SourceRecord] = field(default_factory=list)
    loaded_files: list[str] = field(default_factory=list)

    # ---- building -------------------------------------------------------------------

    @classmethod
    def load(cls, data_dir: Path) -> "Corpus":
        if not data_dir.is_dir():
            raise ConfigError(f"Data folder not found: {data_dir}  (set CORPUS_DIR or use --data-dir)")
        missing = [name for name, _ in loaders.SOURCES if not (data_dir / name).is_file()]
        if missing:
            raise ConfigError(f"Missing source file(s) in {data_dir}: {', '.join(missing)}")

        corpus = cls()
        with_sku: list[SourceRecord] = []
        without_sku: list[SourceRecord] = []
        for name, loader in loaders.SOURCES:  # looked up at call time: new sources need no change here
            records = loader.load(data_dir / name)
            corpus.loaded_files.append(name)
            if name in CATALOGUES:
                corpus.catalogue_skus[name] = [r.sku for r in records if r.sku]
            for rec in records:
                (with_sku if rec.sku else without_sku).append(rec)

        for rec in with_sku:
            corpus._attach(corpus.products.setdefault(rec.sku, Product(rec.sku)), rec)
        for rec in without_sku:
            target, how = corpus._link_without_sku(rec)
            if target is None:
                corpus.unlinked.append(rec)
            else:
                corpus._attach(target, rec)
                target.link_notes.append(f"{rec.source} ({rec.location}) was linked to this SKU by {how}.")
        return corpus

    @staticmethod
    def _attach(product: Product, rec: SourceRecord) -> None:
        product.sources[rec.source] = rec.location
        for name, fact in rec.fields.items():
            product.add(name, fact)

    def _link_without_sku(self, rec: SourceRecord) -> tuple[Product | None, str]:
        if rec.model and rec.variant:
            hits = [
                p for p in self.products.values()
                if any(f.value == rec.model and f.source in CATALOGUES for f in p.values("model"))
                and any(f.value == rec.variant and f.source in CATALOGUES for f in p.values("variant"))
            ]
            if len(hits) == 1:
                return hits[0], f'exact model + variant match ("{rec.model}", "{rec.variant}")'
        if rec.gtin:
            hits = [p for p in self.products.values() if any(f.value == rec.gtin for f in p.values("gtin"))]
            if len(hits) == 1:
                return hits[0], f"exact GTIN match ({rec.gtin})"
        return None, ""

    # ---- querying -------------------------------------------------------------------

    def get(self, sku: str) -> Product | None:
        return self.products.get(sku.strip().upper())

    def similar_skus(self, sku: str, limit: int = 3) -> list[str]:
        return difflib.get_close_matches(sku.strip().upper(), list(self.products), n=limit, cutoff=0.75)

    def catalogue_products(self) -> list[str]:
        """Distinct SKUs listed in at least one catalogue, in file order."""
        seen: dict[str, None] = {}
        for skus in self.catalogue_skus.values():
            for s in skus:
                seen.setdefault(s, None)
        return list(seen)

    def manufacturers(self) -> dict[str, list[str]]:
        """Manufacturer name as written in a source -> SKUs it is stated for."""
        result: dict[str, list[str]] = {}
        for sku, product in self.products.items():
            for name in {f.value for f in product.values("manufacturer")}:
                result.setdefault(name, []).append(sku)
        return result
