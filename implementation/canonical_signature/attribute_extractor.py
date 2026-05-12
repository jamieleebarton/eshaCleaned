from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ExtractionResult:
    residual: str
    head_noun: str
    fluff_stripped: tuple[str, ...]
    form: Optional[str]
    state: Optional[str]
    flavor: Optional[str]
    style: Optional[str]
    packaging: Optional[str]


def _tokenize(text: str) -> list[str]:
    return [t for t in text.replace(",", " ").split() if t]


def extract_attributes(
    text: str,
    *,
    fluff: frozenset[str],
    flavors: frozenset[str],
    forms: frozenset[str],
    states: frozenset[str],
    styles: frozenset[str],
    packaging: frozenset[str],
) -> ExtractionResult:
    tokens = _tokenize(text)
    residual_tokens: list[str] = []
    fluff_stripped: list[str] = []
    form: Optional[str] = None
    state: Optional[str] = None
    flavor: Optional[str] = None
    style: Optional[str] = None
    pkg: Optional[str] = None

    for tok in tokens:
        if tok in fluff:
            fluff_stripped.append(tok)
            continue
        if form is None and tok in forms:
            form = tok
            continue
        if state is None and tok in states:
            state = tok
            continue
        if flavor is None and tok in flavors:
            flavor = tok
            continue
        if style is None and tok in styles:
            style = tok
            continue
        if pkg is None and tok in packaging:
            pkg = tok
            continue
        residual_tokens.append(tok)

    residual = " ".join(residual_tokens)
    head_noun = residual_tokens[-1] if residual_tokens else ""

    return ExtractionResult(
        residual=residual,
        head_noun=head_noun,
        fluff_stripped=tuple(fluff_stripped),
        form=form,
        state=state,
        flavor=flavor,
        style=style,
        packaging=pkg,
    )
