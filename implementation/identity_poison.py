from __future__ import annotations

import re
from dataclasses import dataclass


JUNK_EXACT = {
    "",
    "_",
    "__",
    "___",
    "____",
    "_____",
    "?",
    "??",
    "???",
    "&nbsp",
    "&nbsp;",
    "nbsp",
}

MODIFIER_ONLY_BASES = {
    "additional",
    "all-purpose",
    "as needed",
    "bite-size",
    "bite size",
    "boneless",
    "can",
    "canned",
    "chopped",
    "cold",
    "container",
    "cooked",
    "diced",
    "drained",
    "extra",
    "fat-free",
    "fresh",
    "frozen",
    "garnish",
    "hot",
    "large",
    "less-sodium",
    "low-fat",
    "low-sodium",
    "medium",
    "nonfat",
    "optional",
    "package",
    "peeled",
    "reduced-sodium",
    "sifted",
    "sliced",
    "small",
    "thawed",
    "topping",
    "warm",
    "whole",
}

KNOWN_BAD_BASES = {
    "peache",
}

CONTEXT_PHRASES = (
    "for coating",
    "for deep-fat frying",
    "for deep fat frying",
    "for deep-frying",
    "for dredging",
    "for frying",
    "for garnish",
    "for garnishing",
    "for rolling",
    "for serving",
    "for sprinkling",
    "for topping",
    "to garnish",
    "to serve",
)

BRAND_PREFIXES = (
    "absolut ",
    "betty crocker ",
    "best foods ",
    "campbell's ",
    "campbells ",
    "cool whip ",
    "kraft ",
    "mccormick ",
    "philadelphia ",
    "ritz ",
    "velveeta ",
)


@dataclass(frozen=True)
class PoisonFinding:
    issue: str
    severity: str
    value: str
    repair_hint: str


def clean_identity_text(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = text.replace("\u00a0", " ")
    text = text.replace("&nbsp;", " ")
    text = text.replace("&nbsp", " ")
    text = text.replace("\u2019", "'")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,;:")


def concept_base(concept_key: str | None) -> str:
    return clean_identity_text((concept_key or "").split("|", 1)[0])


def duplicate_adjacent_token(text: str) -> bool:
    words = text.split()
    return any(left == right for left, right in zip(words, words[1:]))


def poison_findings_for_base(base_food: str | None) -> list[PoisonFinding]:
    base = clean_identity_text(base_food)
    findings: list[PoisonFinding] = []

    if base in JUNK_EXACT or re.fullmatch(r"[_?%#*.-]+", base or ""):
        findings.append(PoisonFinding("junk_base", "P0", base, "reject_to_review"))
        return findings

    bad_percent = "%" in base and not re.search(r"\b\d+(?:\.\d+)?%", base)
    if bad_percent or "_" in base or "?" in base or "&nbsp" in base:
        findings.append(PoisonFinding("junk_token_in_base", "P0", base, "repair_or_reject"))

    if base in MODIFIER_ONLY_BASES:
        findings.append(PoisonFinding("modifier_only_base", "P0", base, "reject_or_repair_to_head_food"))

    if base in KNOWN_BAD_BASES:
        findings.append(PoisonFinding("known_bad_base", "P0", base, "repair_to_valid_food_identity"))

    if base.startswith(("additional ", "additonal ", "dditional ")):
        findings.append(PoisonFinding("leading_additional_noise", "P0", base, "strip_additional_preserve_food"))

    if base.startswith(("a ", "an ")) and len(base.split()) > 1:
        findings.append(PoisonFinding("leading_article_base", "P1", base, "strip_article"))

    if duplicate_adjacent_token(base):
        findings.append(PoisonFinding("duplicate_adjacent_token", "P1", base, "dedupe_repeated_token"))

    for phrase in CONTEXT_PHRASES:
        if phrase in base:
            findings.append(PoisonFinding("context_phrase_in_base", "P1", base, "move_to_quantity_or_usage_policy"))
            break

    for prefix in BRAND_PREFIXES:
        if base.startswith(prefix) and len(base.split()) > len(prefix.split()):
            findings.append(PoisonFinding("brand_prefix_in_base", "P2", base, "strip_brand_when_generic_food_remains"))
            break

    return findings


def is_poison_base(base_food: str | None) -> bool:
    return any(finding.severity == "P0" for finding in poison_findings_for_base(base_food))
