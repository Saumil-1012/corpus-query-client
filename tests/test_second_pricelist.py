
import json
import shutil
from types import SimpleNamespace

from corpus_client import loaders
from corpus_client.answer import field_answer, product_info
from corpus_client.index import Corpus
from corpus_client.models import Fact, SourceRecord


def _load_pricelist_b(path):
    """The whole 'new loader': JSON records with sku, supplier, price, currency, valid_from."""
    records = []
    for i, item in enumerate(json.loads(path.read_text(encoding="utf-8")), start=1):
        loc = f"record {i}"
        fields = {name: Fact(item.get(key), path.name, loc, key) for name, key in
                  (("price", "price"), ("currency", "currency"), ("supplier", "supplier"), ("valid_from", "valid_from"))}
        records.append(SourceRecord(path.name, loc, item["sku"].upper(), None, None, None, fields))
    return records


PRICELIST_B = SimpleNamespace(PROVIDES={"price", "currency", "supplier", "valid_from"}, load=_load_pricelist_b)


def test_second_price_list_needs_only_a_loader(tmp_path, monkeypatch, data_dir):
    shutil.copytree(data_dir, tmp_path, dirs_exist_ok=True)
    (tmp_path / "pricelist-b.json").write_text(json.dumps([
        {"sku": "SYN-142-21T", "supplier": "Beta Medical GmbH", "price": "9.20", "currency": "EUR",
         "valid_from": "2026-09-01"},
    ]), encoding="utf-8")
    monkeypatch.setattr(loaders, "SOURCES", loaders.SOURCES + [("pricelist-b.json", PRICELIST_B)])

    corpus = Corpus.load(tmp_path)
    out = field_answer(corpus, "SYN-142-21T", "price")

    assert "2 offers from different sources, kept separate" in out
    assert "9.20 EUR from Beta Medical GmbH, valid from 2026-09-01 [pricelist-b.json, record 1]" in out
    # the original price keeps its OWN (missing) supplier - not borrowed from the other file
    assert "9.80 EUR from supplier not stated, valid from not stated [supplier-pricelist.csv, line 3]" in out
    assert "CONFLICT" not in out and "DISAGREE" not in out
    assert "side by side, not merged or averaged" in out
    assert "2 offers" in product_info(corpus, "SYN-142-21T")
