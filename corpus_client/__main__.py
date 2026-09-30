"""Command-line entry point:  python -m corpus_client --task "<question>" """
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .answer import answer
from .index import Corpus
from .models import ConfigError, CorpusError

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data-engineering-v3"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m corpus_client",
                                 description="Answer questions about the product corpus.")
    ap.add_argument("--task", required=True, help="the question, in plain English")
    ap.add_argument("--parser", choices=["llm", "rules"], default="llm",
                    help="how the question is understood (default: llm)")
    ap.add_argument("--data-dir", type=Path, default=None,
                    help=f"folder with the source files (default: $CORPUS_DIR or {DEFAULT_DATA_DIR.name}/)")
    ap.add_argument("--debug", action="store_true", help="show full error details")
    args = ap.parse_args(argv)

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # .env support is optional; environment variables still work

    # An empty CORPUS_DIR (as in .env.example) means "use the default", not "current folder".
    data_dir = args.data_dir or Path(os.environ.get("CORPUS_DIR") or DEFAULT_DATA_DIR)
    try:
        corpus = Corpus.load(data_dir)
        if args.parser == "llm":
            from . import parser_llm
            try:
                query = parser_llm.parse(args.task)
            except parser_llm.ParseError as exc:
                print(f"Could not understand the question safely: {exc}")
                return 1
        else:
            from . import parser_rules
            query = parser_rules.parse(args.task)

        print(query.describe())
        print()
        print(answer(corpus, query))
        return 0
    except (ConfigError, CorpusError) as exc:
        print(f"Error: {exc}")
        return 2
    except Exception as exc:  # last resort: one clear line instead of a stack trace
        if args.debug:
            raise
        print(f"Unexpected error: {exc.__class__.__name__}: {exc}  (run again with --debug for details)")
        return 3


if __name__ == "__main__":
    sys.exit(main())
