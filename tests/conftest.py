from pathlib import Path

import pytest

from corpus_client.index import Corpus

DATA_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data-engineering-v3"


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture(scope="session")
def corpus() -> Corpus:
    return Corpus.load(DATA_DIR)
