from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.retrieval.bm25 import tokenize


@dataclass(frozen=True)
class ExpandedQuery:
    original: str
    expanded_text: str
    expansion_terms: list[str]
    model_hints: list[str]


DOMAIN_EXPANSIONS: list[tuple[list[str], list[str]]] = [
    (
        [
            "starts then dies",
            "starts and dies",
            "starts and then dies",
            "starts then immediately dies",
            "starts, then immediately dies",
            "starts but dies",
            "starts but stalls",
            "turns on then turns off",
            "engine dies after starting",
        ],
        ["engine starts but stalls", "engine stalls", "check fuel lines"],
    ),
    (
        [
            "red oil warning",
            "oil warning",
            "oil light",
            "oil lamp",
            "oil indicator",
            "low oil pressure indicator",
            "red oil light",
            "oil pressure warning",
        ],
        ["low oil pressure indicator", "engine oil pressure is low", "low oil pr. indicator"],
    ),
    (
        [
            "low oil",
        ],
        [
            "low oil pressure indicator",
            "low oil pr. indicator",
            "engine oil pressure is low",
            "bring the vehicle nearest authorised workshop",
            "during vehicle running",
        ],
    ),
    (
        [
            "stand down",
            "side stand down",
            "stand is down",
            "stand deployed",
            "left the stand down",
            "won't start because stand",
            "will not start because stand",
        ],
        ["side stand", "side stand indicator", "retract the side stand", "vehicle will not start"],
    ),
    (
        [
            "poor pickup",
            "poor pick up",
            "weak acceleration",
            "not picking up speed",
            "not accelerating properly",
            "doesn't pick up",
            "does not pick up",
            "poor acceleration",
            "feels weak",
            "feels slow",
            "loss of pickup",
            "low pickup",
        ],
        ["poor pick up", "poor pickup", "tyre inflation pressure", "under inflated"],
    ),
    (
        [
            "rpm rises but speed does not increase",
            "rpm raises but speed does not increase",
            "rpm rises but speed doesn't increase",
        ],
        ["poor pickup", "engine rpm raises disproportionately", "adjust the clutch free play"],
    ),
    (
        [
            "bike jerks",
            "jerks while accelerating",
            "choking during acceleration",
            "hesitates while accelerating",
        ],
        ["poor pick up", "poor pickup", "air cleaner element", "spark plug", "fuel lines"],
    ),

    (
        [
            "engine oil level",
            "check engine oil",
            "checking engine oil",
            "oil level",
        ],
        ["engine oil level", "gauge oil level", "dipstick"],
    ),
    (
        [
            "not starting",
            "won't start",
            "will not start",
            "does not start",
            "engine won't turn on",
        ],
        ["engine does not start", "starting the engine", "ignition switch"],
    ),
]


MODEL_ALIASES: dict[str, list[str]] = {
    "pulsar n160": ["pulsar n160", "pulsar n 160"],
    "pulsar ns160": ["pulsar ns160", "pulsar ns 160", "ns160", "ns 160"],
    "dominar": ["dominar", "dominar 250"],
    "tvs sport": ["tvs sport", "sport"],
    "tvs apache rr 310": ["apache rr 310", "rr 310", "tvs apache rr310", "tvs apache rr 310"],
    "splendor": ["splendor"],
    "glamour": ["glamour"],
    "hf deluxe": ["hf deluxe", "hf-deluxe"],
    "classic 350": ["classic 350", "all new classic 350"],
    "himalyan 450": ["himalayan 450", "himalyan 450", "himalayan"],
}


def _contains_phrase(query: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", query, flags=re.I) is not None


def detect_model_hints(query: str) -> list[str]:
    lowered = query.lower()
    hints: list[str] = []
    for canonical, aliases in MODEL_ALIASES.items():
        if any(_contains_phrase(lowered, alias) for alias in aliases):
            hints.append(canonical)
    return hints


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen = set()
    for value in values:
        normalized = value.lower()
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(value)
    return deduped


def expand_query(query: str) -> ExpandedQuery:
    lowered = query.lower()
    expansions: list[str] = []

    for triggers, terms in DOMAIN_EXPANSIONS:
        if any(_contains_phrase(lowered, trigger) for trigger in triggers):
            expansions.extend(terms)

    model_hints = detect_model_hints(query)
    for canonical in model_hints:
        expansions.append(canonical)
        expansions.extend(MODEL_ALIASES[canonical])

    deduped = _dedupe(expansions)
    expanded_text = " ".join([query, *deduped]).strip()
    return ExpandedQuery(
        original=query,
        expanded_text=expanded_text,
        expansion_terms=deduped,
        model_hints=model_hints,
    )


def expansion_token_overlap(expanded: ExpandedQuery, text: str) -> float:
    if not expanded.expansion_terms:
        return 0.0
    haystack = text.lower()
    phrase_hits = sum(1 for term in expanded.expansion_terms if term.lower() in haystack)
    query_tokens = set(tokenize(expanded.expanded_text))
    text_tokens = set(tokenize(text))
    token_hits = len(query_tokens & text_tokens) / max(1, len(query_tokens))
    phrase_score = phrase_hits / len(expanded.expansion_terms)
    return min(1.0, 0.65 * phrase_score + 0.35 * token_hits)
