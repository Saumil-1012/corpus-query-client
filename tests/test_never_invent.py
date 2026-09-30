"""The behaviour we care about most: never print a value that is not in the files."""
import csv
import json
import re

from corpus_client.answer import product_info


def _source_text(data_dir, fact) -> str:
    """The raw text of the exact row/record a Fact claims to come from."""
    path = data_dir / fact.source
    number = int(re.search(r"\d+", fact.location).group())
    if fact.source.endswith(".csv"):
        return path.read_text(encoding="utf-8").splitlines()[number - 1]
    if fact.source.endswith(".json"):
        return json.dumps(json.loads(path.read_text(encoding="utf-8"))[number - 1], ensure_ascii=False)
    if fact.source.endswith(".html"):
        return re.findall(r"<tr><td>.*?</tr>", path.read_text(encoding="utf-8"))[number - 1]
    if fact.source.endswith(".xml"):
        return re.findall(r"<item>.*?</item>", path.read_text(encoding="utf-8"), re.S)[number - 1]
    raise AssertionError(fact.source)


def test_every_value_is_found_in_the_row_it_cites(corpus, data_dir):
    """For all 123 SKUs and every field: the value (as written in the file) must be present in
    exactly the file row the client cites. This catches invented values AND wrong joins."""
    checked = 0
    for product in corpus.products.values():
        for facts in product.facts.values():
            for fact in facts:
                if fact.is_blank or fact.column == "package":
                    continue
                as_written = fact.raw or fact.value
                row = _source_text(data_dir, fact).replace("&amp;", "&")
                assert as_written in row, f"{product.sku}: {as_written!r} not in {fact.where}"
                checked += 1
    assert checked > 600  # 663 values today; guards against the test silently checking nothing


def test_unknown_fields_are_reported_not_filled(corpus):
    out = product_info(corpus, "SYN-261-38X")
    says, _, does_not = out.partition("WHAT THE CORPUS DOES NOT SAY")
    assert "EUR" not in says and "GTIN" not in says and "Manufacturer" not in says
    for label in ("Manufacturer", "Price", "GTIN", "PZN", "Packaging", "Technical specs"):
        assert label in does_not
    # brand name is not turned into a manufacturer, even though NimbusCare Supplies BV exists in the price list
    assert "NimbusCare Supplies BV" not in out


def test_empty_cell_is_not_copied_from_a_similar_product(corpus):
    # SYN-394-27U and SYN-184-27U share gauge 27 and length 60, but 394's diameter cell is empty.
    out = product_info(corpus, "SYN-394-27U")
    assert "0.41" not in out
    assert "EMPTY IN SOURCE - the cell is empty in supplier-pricelist.csv, line 9" in out


def test_unknown_sku_says_so_and_suggests_without_assuming(corpus):
    out = product_info(corpus, "SYN-180-17S")
    assert 'No product with seller SKU "SYN-180-17S"' in out
    assert "SYN-180-17" in out and "not assumed to be the same product" in out
