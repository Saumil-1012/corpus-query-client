
from __future__ import annotations

import json
import os

from .models import ConfigError
from .query import FIELD_LABELS, INTENTS, SCOPES, Query

DEFAULT_PROVIDER = "azure"
DEFAULT_AZURE_DEPLOYMENT = "gpt-4.1-mini"
DEFAULT_AZURE_API_VERSION = "2024-10-21"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You translate a procurement colleague's question about a product catalogue \
into a structured query by calling the tool `route_question`. You do NOT have the product \
data and you must never answer the question or guess any product value.

Rules:
- Copy seller SKUs (format like SYN-000-00A) and manufacturer names exactly as written in the question.
- "information", "details", "what do we know about <SKU>" -> intent product_info.
- A single attribute of one SKU (price, GTIN, PZN, packaging, manufacturer, a spec) -> intent field.
- "which products are made/manufactured by <X>" -> intent by_manufacturer.
- "how many products" -> intent count_products. Use scope "all" unless a specific catalogue file is named.
- Anything else (comparisons, recommendations, questions without an SKU where one is needed, \
questions not about the catalogue) -> intent unsupported, with a short reason in note."""

TOOL_NAME = "route_question"
TOOL_DESCRIPTION = "Structured form of the user's question. Fill only what the question states."
TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "sku": {"type": "string", "description": "Seller SKU exactly as written in the question"},
        "field": {"type": "string", "enum": list(FIELD_LABELS)},
        "manufacturer": {"type": "string", "description": "Manufacturer name exactly as written"},
        "scope": {"type": "string", "enum": list(SCOPES)},
        "note": {"type": "string", "description": "Only for intent=unsupported: why"},
    },
    "required": ["intent"],
}


class ParseError(Exception):
    """The LLM returned something we refuse to use."""


def parse(question: str, client=None, provider: str | None = None) -> Query:
    provider = (provider or os.environ.get("LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if provider == "azure":
        data, label = _ask_azure(question, client)
    elif provider == "anthropic":
        data, label = _ask_anthropic(question, client)
    else:
        raise ConfigError(f'LLM_PROVIDER must be "azure" or "anthropic", not "{provider}".')
    return validate(data, question, parsed_by=label)


# ---- Azure OpenAI ------------------------------------------------------------------------

def _ask_azure(question: str, client) -> tuple[dict, str]:
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT") or DEFAULT_AZURE_DEPLOYMENT
    if client is None:
        client = _make_azure_client()
    import openai

    request = dict(
        model=deployment,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": question}],
        tools=[{"type": "function", "function": {
            "name": TOOL_NAME, "description": TOOL_DESCRIPTION, "parameters": TOOL_PARAMETERS}}],
        tool_choice={"type": "function", "function": {"name": TOOL_NAME}},
    )
    try:
        try:
            response = client.chat.completions.create(**request, temperature=0, max_tokens=300)
        except openai.BadRequestError as exc:
            # Newer reasoning models (GPT-5 family, o-series) reject temperature/max_tokens.
            if "temperature" not in str(exc) and "max_tokens" not in str(exc):
                raise
            response = client.chat.completions.create(**request, max_completion_tokens=4000)
    except openai.AuthenticationError:
        raise ConfigError("AZURE_OPENAI_API_KEY was rejected. Check the key and endpoint in your .env file.")
    except openai.NotFoundError:
        raise ConfigError(f'Azure deployment "{deployment}" not found. Set AZURE_OPENAI_DEPLOYMENT to the '
                          "deployment name shown in Azure AI Foundry.")
    except openai.APIConnectionError:
        raise ConfigError("Could not reach Azure OpenAI (network or wrong AZURE_OPENAI_ENDPOINT).")
    except openai.APIError as exc:
        raise ConfigError(f"Azure OpenAI error: {exc.__class__.__name__}. Try again, or use --parser rules.")

    calls = response.choices[0].message.tool_calls or []
    if not calls:
        raise ParseError("The language model did not return a structured query.")
    try:
        data = json.loads(calls[0].function.arguments)
    except (json.JSONDecodeError, TypeError):
        raise ParseError("The language model returned a malformed structured query.")
    return data, f"Azure OpenAI {deployment}"


def _make_azure_client():
    missing = [v for v in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT") if not os.environ.get(v)]
    if missing:
        raise ConfigError(f"{' and '.join(missing)} not set. Copy .env.example to .env and fill it in "
                          "(or run with --parser rules to work without an LLM).")
    try:
        from openai import AzureOpenAI
    except ImportError:
        raise ConfigError("The 'openai' package is not installed. Run: pip install -r requirements.txt")
    return AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION") or DEFAULT_AZURE_API_VERSION,
    )


# ---- Anthropic ---------------------------------------------------------------------------

def _ask_anthropic(question: str, client) -> tuple[dict, str]:
    model = os.environ.get("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
    if client is None:
        client = _make_anthropic_client()
    import anthropic

    try:
        response = client.messages.create(
            model=model,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            tools=[{"name": TOOL_NAME, "description": TOOL_DESCRIPTION, "input_schema": TOOL_PARAMETERS}],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": question}],
        )
    except anthropic.AuthenticationError:
        raise ConfigError("ANTHROPIC_API_KEY was rejected by the API. Check the key in your .env file.")
    except anthropic.NotFoundError:
        raise ConfigError(f'Model "{model}" not found. Set ANTHROPIC_MODEL to a model your key can use.')
    except anthropic.APIConnectionError:
        raise ConfigError("Could not reach the Anthropic API (network). Try again, or use --parser rules.")
    except anthropic.APIError as exc:
        raise ConfigError(f"Anthropic API error: {exc.__class__.__name__}. Try again, or use --parser rules.")

    calls = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
    if not calls:
        raise ParseError("The language model did not return a structured query.")
    return calls[0].input, f"Anthropic {model}"


def _make_anthropic_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ConfigError("ANTHROPIC_API_KEY not set. Copy .env.example to .env and fill it in "
                          "(or run with --parser rules to work without an LLM).")
    try:
        import anthropic
    except ImportError:
        raise ConfigError("The 'anthropic' package is not installed. Run: pip install anthropic")
    return anthropic.Anthropic()


# ---- shared: never trust the LLM's form blindly ------------------------------------------

def validate(data: dict, question: str, parsed_by: str) -> Query:
    """Turn the LLM's form into a Query, refusing anything not grounded in the question."""
    intent = data.get("intent")
    if intent not in INTENTS:
        raise ParseError(f"The language model returned an unknown intent: {intent!r}.")

    q_lower = question.lower()
    sku = (data.get("sku") or "").strip() or None
    if sku and sku.lower() not in q_lower:
        raise ParseError(f'The language model returned SKU "{sku}", which is not in your question. Refusing to use it.')
    manufacturer = (data.get("manufacturer") or "").strip() or None
    if manufacturer and manufacturer.lower() not in q_lower:
        raise ParseError(f'The language model returned manufacturer "{manufacturer}", which is not in your '
                         "question. Refusing to use it.")

    field = data.get("field")
    if field is not None and field not in FIELD_LABELS:
        field = None
    scope = data.get("scope") if data.get("scope") in SCOPES else "all"

    # An intent that needs an argument the question did not provide becomes "unsupported".
    if intent in ("product_info", "field") and not sku:
        return Query("unsupported", note="the question does not name a seller SKU", parsed_by=parsed_by)
    if intent == "field" and not field:
        return Query("unsupported", note="it is not clear which attribute is asked for", parsed_by=parsed_by)
    if intent == "by_manufacturer" and not manufacturer:
        return Query("unsupported", note="the question does not name a manufacturer", parsed_by=parsed_by)

    return Query(intent=intent, sku=sku.upper() if sku else None, field=field,
                 manufacturer=manufacturer, scope=scope, note=data.get("note"), parsed_by=parsed_by)
