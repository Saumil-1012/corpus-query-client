"""Loading and joining: are the files read completely and linked only on exact keys?"""
from corpus_client import normalise as n


def test_every_row_of_every_file_is_loaded(corpus):
    assert len(corpus.catalogue_skus["catalogue-a.html"]) == 3
    assert len(corpus.catalogue_skus["catalogue-b.html"]) == 120
    in_file = lambda name: sum(1 for p in corpus.products.values() if name in p.sources)
    assert in_file("supplier-pricelist.csv") == 14
    assert in_file("manufacturer-specs.json") == 5
    assert in_file("distributor-feed.xml") == 4
    assert corpus.unlinked == []


def test_specs_are_linked_by_exact_model_and_variant(corpus):
    p = corpus.get("SYN-142-21T")
    assert p.sources["manufacturer-specs.json"] == "record 2"
    assert "exact model + variant" in p.link_notes[0]
    # SYN-352-21T has the same variant "21 T" but a different model -> must NOT get the specs
    assert "manufacturer-specs.json" not in corpus.get("SYN-352-21T").sources


def test_blank_cells_stay_blank(corpus):
    # supplier-pricelist.csv line 8: connector empty; line 9: outer diameter empty
    assert corpus.get("SYN-352-21T").values("connector") == []
    assert len(corpus.get("SYN-352-21T").blanks("connector")) == 1
    assert corpus.get("SYN-394-27U").values("outer_diameter_mm") == []


def test_normalisation_only_changes_formatting():
    assert n.sterility("ja") == "sterile" and n.sterility("nein") == "non_sterile"
    assert n.connector("Luer-Lock") == n.connector("luer_lock") == "luer_lock"
    assert n.number("0.10") == n.number("0,1") == "0.1"
    assert n.price("9,8") == "9.80"
    assert n.number("") is None


def test_gtin_check_digit():
    assert n.gtin_check_digit_ok("4006381333931") == (True, 1)     # a valid EAN-13
    assert n.gtin_check_digit_ok("04012345000011") == (False, 6)   # from the corpus
    assert n.gtin_check_digit_ok("12345")[0] is False
