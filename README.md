# Corpus client — Recall Space home assignment

A small Python command-line tool that answers questions about the five product files in
`fixtures/data-engineering-v3/`. It prints only values that exist in the files, always says
**which file and row** each value came from, and says plainly what is **missing and why**.

```bash
python -m corpus_client --task "what is the price of SYN-142-21T?"
```

The written answers are in **`ANSWERS.md`**; the real output for the five tasks is in **`transcript.md`**.

---

## Run it (unzip → install → configure → run)

Needs Python 3.11+.

```bash
cd recall-corpus-client
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then fill in AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT
python -m corpus_client --task "get the information on seller sku SYN-261-38X"
```

- **LLM provider:** Azure OpenAI. **Model:** `gpt-4.1-mini` (deployment name via `AZURE_OPENAI_DEPLOYMENT`).
  To use Anthropic instead: `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` (model `claude-haiku-4-5-20251001`).
- **Missing key** → one line: `Error: AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT not set ...` (exit code 2), no stack trace.
- **Without a key:** `--parser rules` uses simple keyword rules instead of the LLM. It understands the
  five tasks but far fewer phrasings. The answer part is identical in both modes.
- Optional flags: `--parser {llm,rules}`, `--data-dir PATH` (or `CORPUS_DIR`), `--debug`.
- Tests: `python -m pytest` (32 tests, no API key or network needed — the LLM is replaced by a fake).
- Transcript: `./make_transcript.sh` runs the five tasks and writes `transcript.md`.

## How it is structured

| File | Job |
| --- | --- |
| `corpus_client/loaders/*.py` | One reader per file format. Turns each row into values tagged with file + row. `loaders/__init__.py` lists the files. |
| `corpus_client/normalise.py` | Formatting only: `ja`→`sterile`, `Luer-Lock`→`luer_lock`, `0.10`→`0.1`, GTIN check digit. Never fills anything in. |
| `corpus_client/index.py` | Joins everything per seller SKU. Spec records (no SKU) join only on exact model + variant, else exact GTIN, else "unlinked". |
| `corpus_client/parser_llm.py` | Sends **only the question text** to the LLM (Azure OpenAI or Anthropic), which fills a fixed form (intent, SKU, field…). SKU/manufacturer it returns must appear in the question, or it is rejected. |
| `corpus_client/parser_rules.py` | Keyword alternative to the LLM (`--parser rules`), used by the tests. |
| `corpus_client/answer.py` | Deterministic answers: values with sources, gaps with reasons, warnings. |
| `corpus_client/__main__.py` | The `--task` command line; turns every error into one readable line. |

Why the LLM only parses the question and never sees the data: the one rule that matters most is
"never invent data". A language model that writes the answer can invent; code that can only print
cells from the files cannot. The LLM adds value where rules are weak (understanding free phrasing),
and is kept away from where it is risky (values). See ANSWERS.md, Q1 and Q5.

## Assumptions (the brief leaves these open; decided and written down)

1. **A "product" is one distinct seller SKU in a catalogue.** "The catalogue" = `catalogue-a.html` +
   `catalogue-b.html` together (3 + 120 = 123, no overlap). The other files describe products, they don't add new ones.
2. **catalogue-a's SKUs are separate products,** not typos of catalogue-b: different format
   (`SYN-180-17`, no trailing letter) and different model numbers (RecallSafe 180/204/260) that exist nowhere else.
3. **A brand is not a manufacturer.** "RecallFlex 191" is not assumed to be made by RecallFlex Medical AG;
   only rows that state the manufacturer count.
4. **Specs are joined only on exact model + variant** (e.g. "RecallSafe 142" + "21 T"). Same variant with a
   different model (SYN-352-21T) gets nothing.
5. **Prices are shown exactly as listed** (EUR). No unit is assumed, because the price list does not state one.
6. **Invalid GTINs are shown, not corrected or hidden** — with a warning.
7. **Empty cells stay empty**, even when a near-identical product has a value (SYN-394-27U vs SYN-184-27U).
8. The source files are included unchanged in `fixtures/` so the zip runs as-is.

## Known limitations / what is not built

- The whole corpus is re-read on every call (fine for 130 rows; see ANSWERS.md Q4 for what changes at scale).
- The LLM path is tested with a fake client plus the five real transcript runs; there is no larger evaluation
  set of phrasings. The rules parser is narrow by design.
- Prices carry a *supplier* and *valid-from* date, but today's price list states neither, so both print as
  "not stated". A second price list is shown side by side (see `tests/test_second_pricelist.py`); prices in
  different units (per piece vs per box) are shown, not converted.
- The HTML loader expects exactly the catalogue column set and stops with a clear error otherwise;
  the CSV loader ignores columns it does not know (see ANSWERS.md Q5 on why that matters).
- Output is English only; questions in German work only through the LLM parser.

## Time and tools

- Time spent: about 5–6 hours (corpus analysis, code, tests, writing).
- AI tools: I used Claude as a coding assistant: to cross-check the five files with a script, to draft code
  and tests, and to review wording. The design decisions (LLM only parses the question and never sees data,
  brand ≠ manufacturer, empty cells stay empty, joins only on exact keys) and the answers in ANSWERS.md are
  mine, and I can explain and defend every line.
- The client itself uses Azure OpenAI (gpt-4.1-mini) only to parse the question. I chose a small, fast model on purpose: it only fills in a form, never produces the answer, so a larger model would add latency and cost without making answers better.
