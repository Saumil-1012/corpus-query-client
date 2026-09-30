"""The five assignment tasks end-to-end, and the LLM parser with a fake API client."""
import json
from types import SimpleNamespace

import pytest

from corpus_client import parser_llm
from corpus_client.__main__ import main

TASKS = {
    "get the information on seller sku SYN-261-38X":
        {"intent": "product_info", "sku": "SYN-261-38X"},
    "what is the price of SYN-142-21T?":
        {"intent": "field", "sku": "SYN-142-21T", "field": "price"},
    "which products are made by RecallFlex Medical AG?":
        {"intent": "by_manufacturer", "manufacturer": "RecallFlex Medical AG"},
    "how many products are in the catalogue?":
        {"intent": "count_products", "scope": "all"},
    "what is the GTIN of SYN-100-15S?":
        {"intent": "field", "sku": "SYN-100-15S", "field": "gtin"},
}

EXPECTED = {
    "get the information on seller sku SYN-261-38X": ["Found in 1 of 5 files", "NimbusCare 261", "NOT IN CORPUS"],
    "what is the price of SYN-142-21T?": ["9.80 EUR", "supplier-pricelist.csv, line 3", "box of 12"],
    "which products are made by RecallFlex Medical AG?": ['"RecallFlex Medical AG": 2', "SYN-107-16T",
                                                          "SYN-149-22U", "18 more catalogue products"],
    "how many products are in the catalogue?": ["123 distinct seller SKUs", "120 rows", "3 rows"],
    "what is the GTIN of SYN-100-15S?": ["04012345000011", "2 sources agree", "fails the GS1 check-digit"],
}


class FakeAnthropic:
    """Stands in for anthropic.Anthropic(): returns a fixed tool call, records what was sent."""

    def __init__(self, tool_input):
        self.tool_input, self.sent = tool_input, None
        self.messages = self

    def create(self, **kwargs):
        self.sent = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=self.tool_input)])


class FakeAzure:
    """Stands in for openai.AzureOpenAI(): same idea, OpenAI response shape."""

    def __init__(self, tool_input):
        self.tool_input, self.sent = tool_input, None
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.sent = kwargs
        call = SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(self.tool_input)))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))])


def _sent_user_content(provider, sent):
    msgs = sent["messages"]
    return [m for m in msgs if m["role"] == "user"], (sent.get("system", "") + str(msgs) + str(sent["tools"]))


@pytest.mark.parametrize("task", TASKS)
def test_five_tasks_with_rules_parser(task, capsys):
    assert main(["--parser", "rules", "--task", task]) == 0
    out = capsys.readouterr().out
    for expected in EXPECTED[task]:
        assert expected in out, f"{expected!r} missing for {task!r}"


@pytest.mark.parametrize("provider,fake", [("azure", FakeAzure), ("anthropic", FakeAnthropic)])
@pytest.mark.parametrize("task", TASKS)
def test_llm_parser_only_sends_the_question(task, provider, fake, corpus):
    client = fake(TASKS[task])
    query = parser_llm.parse(task, client=client, provider=provider)
    assert query.intent == TASKS[task]["intent"]
    # the only user content sent to the API is the question itself - no corpus data anywhere
    user_msgs, everything_sent = _sent_user_content(provider, client.sent)
    assert user_msgs == [{"role": "user", "content": task}]
    fixed_part = everything_sent.replace(task, "")
    assert not any(sku in fixed_part for sku in corpus.products)
    assert not any(name in fixed_part for name in corpus.manufacturers())
    assert "EUR" not in fixed_part


@pytest.mark.parametrize("provider,fake", [("azure", FakeAzure), ("anthropic", FakeAnthropic)])
def test_llm_cannot_introduce_an_sku_that_is_not_in_the_question(provider, fake):
    client = fake({"intent": "field", "sku": "SYN-142-21T", "field": "price"})
    with pytest.raises(parser_llm.ParseError, match="not in your question"):
        parser_llm.parse("what is the price of the training cannula?", client=client, provider=provider)


def test_llm_intent_without_required_argument_becomes_unsupported():
    q = parser_llm.validate({"intent": "field", "field": "price"}, "what does it cost?", "test")
    assert q.intent == "unsupported"


def test_missing_api_key_is_one_clear_line(monkeypatch, capsys):
    for var in ("LLM_PROVIDER", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None, raising=False)
    assert main(["--task", "what is the price of SYN-142-21T?"]) == 2
    out = capsys.readouterr().out.strip()
    assert out.startswith("Error: AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT not set") and "\n" not in out


def test_missing_data_folder_is_one_clear_line(capsys, tmp_path):
    assert main(["--parser", "rules", "--data-dir", str(tmp_path / "nope"), "--task", "x"]) == 2
    assert capsys.readouterr().out.startswith("Error: Data folder not found")


def test_azure_retries_without_temperature_for_reasoning_models():
    """GPT-5-family deployments reject temperature/max_tokens; the parser retries once without them."""
    import openai

    def bad_request(message):
        # Build the SDK's error without depending on its HTTP library (httpx vs httpx2 differs by version).
        err = openai.BadRequestError.__new__(openai.BadRequestError)
        Exception.__init__(err, message)
        return err

    class PickyAzure(FakeAzure):
        def create(self, **kwargs):
            if "temperature" in kwargs:
                raise bad_request("Unsupported parameter: 'temperature'")
            assert "max_completion_tokens" in kwargs
            return super().create(**kwargs)

    task = "what is the price of SYN-142-21T?"
    query = parser_llm.parse(task, client=PickyAzure(TASKS[task]), provider="azure")
    assert (query.intent, query.sku, query.field) == ("field", "SYN-142-21T", "price")


def test_empty_env_values_from_env_example_fall_back_to_defaults(monkeypatch, capsys):
    """.env.example leaves CORPUS_DIR empty; that must mean 'default folder', not 'current folder'."""
    monkeypatch.setenv("CORPUS_DIR", "")
    assert main(["--parser", "rules", "--task", "how many products are in the catalogue?"]) == 0
    assert "123 distinct seller SKUs" in capsys.readouterr().out
