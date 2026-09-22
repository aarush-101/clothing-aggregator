"""Query validation and prompt-injection defence.

A search box that feeds an LLM is an injection surface. Three layers protect
it:

1. **Validation** - length, character and emptiness checks before anything else.
2. **Neutralisation** - the characters used to delimit our prompt sections are
   stripped from user text so it cannot close a tag and start "speaking" as the
   system.
3. **Detection + downgrade** - recognisably adversarial queries skip the LLM
   entirely and are parsed by the deterministic parser instead.

The last line of defence lives elsewhere: the model's reply is parsed into a
strict Pydantic model, so even a fully hijacked response can only ever produce
search filters.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple

MAX_REASONABLE_WORDS = 80


class QueryValidationError(ValueError):
    """Raised when a search query cannot be accepted at all."""


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")
# Characters used for prompt structure, plus zero-width/bidi characters that
# can hide instructions from a human reviewer.
_STRUCTURAL = re.compile(r"[<>{}\[\]`\\|​-‏‪-‮⁠-⁤﻿]")

_INJECTION_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "override_instructions",
        re.compile(
            r"\b(ignore|disregard|forget|override|bypass)\b[^.]{0,40}\b"
            r"(previous|prior|above|earlier|all|your|the)\b[^.]{0,20}"
            r"\b(instruction|instructions|prompt|prompts|rule|rules|context)\b",
            re.I,
        ),
    ),
    (
        "role_reassignment",
        re.compile(
            r"\b(you are now|act as|pretend to be|from now on you|new persona|"
            r"roleplay as|behave as)\b",
            re.I,
        ),
    ),
    (
        "prompt_exfiltration",
        re.compile(
            r"\b(system prompt|your (instructions|prompt|rules|guidelines)|"
            r"reveal|repeat back|print|output|show me)\b[^.]{0,30}"
            r"\b(prompt|instructions|system|configuration|api key|secret|token)\b",
            re.I,
        ),
    ),
    ("fake_turn", re.compile(r"(^|\s)(system|assistant|human|user)\s*:\s", re.I)),
    (
        "tag_injection",
        re.compile(r"</?\s*(system|assistant|human|user|search_query|instructions?)\s*>", re.I),
    ),
    (
        "tool_manipulation",
        re.compile(
            r"\b(tool_use|function_call|call the tool|invoke the function|"
            r"stop_reason|end_turn)\b",
            re.I,
        ),
    ),
    (
        "exfiltration_target",
        re.compile(
            r"\b(send|post|fetch|curl|http requests?)\b[^.]{0,30}\b(to|at)\b\s*https?://", re.I
        ),
    ),
]


def normalise_query(raw: str, max_length: int, min_length: int = 2) -> str:
    """Validate and canonicalise a raw search query.

    Raises :class:`QueryValidationError` when the query is unusable.
    """
    if raw is None:
        raise QueryValidationError("Search query is required.")
    text = unicodedata.normalize("NFKC", str(raw))
    text = _CONTROL_CHARS.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()
    if not text:
        raise QueryValidationError("Search query is required.")
    if len(text) < min_length:
        raise QueryValidationError(f"Search query must be at least {min_length} characters.")
    if len(text) > max_length:
        raise QueryValidationError(
            f"Search query must be {max_length} characters or fewer (received {len(text)})."
        )
    if len(text.split(" ")) > MAX_REASONABLE_WORDS:
        raise QueryValidationError(f"Search query must be {MAX_REASONABLE_WORDS} words or fewer.")
    return text


def detect_injection(text: str) -> List[str]:
    """Return the names of any injection heuristics that fired."""
    return [name for name, pattern in _INJECTION_PATTERNS if pattern.search(text or "")]


def neutralise_for_prompt(text: str) -> str:
    """Make user text safe to embed inside a delimited prompt section."""
    cleaned = _STRUCTURAL.sub(" ", text or "")
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    return cleaned


def should_bypass_llm(text: str) -> Tuple[bool, List[str]]:
    """Decide whether to skip the LLM for this query.

    Anything that looks like an instruction to the model rather than a shopping
    request is parsed deterministically instead - cheaper, and it removes the
    attack surface entirely.
    """
    matches = detect_injection(text)
    return (len(matches) > 0, matches)
