"""Numeric-provenance guardrail (plan §2.2 layer 4). The backstop that makes
the "LLM never generates a dollar figure" constraint hold even if every
other layer (type system, output schema, system instruction) somehow fails
or is bypassed by a manipulated model.

Deliberately NOT a regex string match against tool output. Comparing on
canonical Decimal values (not substrings) means:
  - $1,250.00, $1250, and 1250.00 are all recognized as the same value.
  - A non-currency number that happens to look like a dollar amount only
    fails the check if it genuinely isn't present anywhere in the tool
    payload -- not because of incidental formatting differences.

Lives in shared/ rather than agent/csr_agent/ or bff/app/ deliberately: the
Agent Engine deployment and the BFF are two separately-built Docker images
with separate requirements.txt, so this needs a location neither service's
package "owns" -- both agent/Dockerfile and bff/Dockerfile COPY shared/
into their build context (see infra notes in docs/architecture). Zero
dependencies beyond the standard library, so it's cheap to vendor into both
images without pulling in either service's full dependency tree.
"""
from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

CENTS = Decimal("0.01")

# Matches $-prefixed currency tokens: "$1,250.00", "$1250", "$0.20", "$ 470".
# Deliberately does NOT match bare numbers without a leading "$" -- an LLM
# asserting a dollar figure without the currency marker at all is a
# separate (also bad) failure mode, but conflating it here would produce
# false positives on ordinary numbers in the message (dates, percentages,
# CPT codes) that were never claimed to be currency.
CURRENCY_TOKEN_RE = re.compile(r"\$\s?[\d][\d,]*(?:\.\d{1,2})?")


@dataclass
class GuardrailResult:
    passed: bool
    checked_tokens: list[str] = field(default_factory=list)
    violating_tokens: list[str] = field(default_factory=list)


def extract_currency_tokens(text: str) -> list[str]:
    return CURRENCY_TOKEN_RE.findall(text)


def normalize_currency(token: str) -> Decimal | None:
    cleaned = token.replace("$", "").replace(",", "").strip()
    try:
        return Decimal(cleaned).quantize(CENTS)
    except InvalidOperation:
        return None


def _collect_decimal_values(obj) -> set[Decimal]:
    """Recursively walk a JSON-mode-serialized payload (dict/list/str/int/
    float/bool/None) and collect every leaf that parses as a Decimal.
    Pydantic's model_dump(mode="json") renders Decimal fields as strings
    (e.g. "1250.00"), so this is a string/number walk, not a type check."""
    found: set[Decimal] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            found |= _collect_decimal_values(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            found |= _collect_decimal_values(v)
    elif isinstance(obj, bool):
        pass  # bool is a subclass of int -- explicitly exclude, not a number
    elif isinstance(obj, (int, float)):
        found.add(Decimal(str(obj)).quantize(CENTS))
    elif isinstance(obj, str):
        with contextlib.suppress(InvalidOperation):
            found.add(Decimal(obj).quantize(CENTS))
    return found


def verify_numeric_provenance(agent_text: str, tool_payloads: list[dict]) -> GuardrailResult:
    """The core check: every $-token in agent_text must equal (after
    canonical Decimal normalization) some value that genuinely appears
    somewhere in tool_payloads. tool_payloads should be the JSON-mode dumps
    of every tool result returned during this turn (plan §2.2: "checked
    against the set of Decimal-normalized values actually present in the
    referenced tool payload(s)")."""
    known_values: set[Decimal] = set()
    for payload in tool_payloads:
        known_values |= _collect_decimal_values(payload)

    tokens = extract_currency_tokens(agent_text)
    violating = []
    for token in tokens:
        value = normalize_currency(token)
        if value is None or value not in known_values:
            violating.append(token)

    return GuardrailResult(passed=not violating, checked_tokens=tokens, violating_tokens=violating)
