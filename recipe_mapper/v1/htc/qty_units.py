"""Quantity + unit extractor for recipe ingredient `display` strings.

Handles: "1 1/2 cups sugar", "1/4 tsp salt", "2 tablespoons olive oil",
         "3 cloves garlic", "1 (15 oz) can tomatoes".
Returns (qty, unit) where unit is normalized to the same vocab the
gram-weight resolver uses (cup, tbsp, tsp, oz, fl_oz, g, kg, lb, ml, l,
quart, pint, gallon, dash, pinch, slice, stick, package, serving, piece).
"""
from __future__ import annotations

import re
from fractions import Fraction


# common unicode fractions
UNI_FRAC = {
    "½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4",
    "⅕": "1/5", "⅖": "2/5", "⅗": "3/5", "⅘": "4/5",
    "⅙": "1/6", "⅚": "5/6", "⅐": "1/7", "⅛": "1/8", "⅜": "3/8",
    "⅝": "5/8", "⅞": "7/8", "⅑": "1/9", "⅒": "1/10",
}

UNIT_NORM = [
    (re.compile(r"\b(?:cups?|c\.)\b", re.I), "cup"),
    (re.compile(r"\b(?:tablespoons?|tbsp\.?|tbs\.?|tbl\.?|T\b)", re.I), "tbsp"),
    (re.compile(r"\b(?:teaspoons?|tsp\.?|ts\.?|t\b)", re.I), "tsp"),
    (re.compile(r"\b(?:fluid ounces?|fl\.?\s*oz\.?|fl)\b", re.I), "fl_oz"),
    (re.compile(r"\b(?:ounces?|oz\.?)\b", re.I), "oz"),
    (re.compile(r"\bmilliliters?\b|\bmls?\b|\bml\.?\b", re.I), "ml"),
    (re.compile(r"\bliters?\b|\blitres?\b|\bL\b", re.I), "l"),
    (re.compile(r"\bgrams?\b|\bg\b|\bgr\b", re.I), "g"),
    (re.compile(r"\bkilograms?\b|\bkg\b", re.I), "kg"),
    (re.compile(r"\bpounds?\b|\blbs?\.?\b|\b#\b", re.I), "lb"),
    (re.compile(r"\bquarts?\b|\bqts?\.?\b", re.I), "quart"),
    (re.compile(r"\bpints?\b|\bpts?\.?\b", re.I), "pint"),
    (re.compile(r"\bgallons?\b|\bgal\.?\b", re.I), "gallon"),
    (re.compile(r"\bdash(?:es)?\b", re.I), "dash"),
    (re.compile(r"\bpinch(?:es)?\b", re.I), "pinch"),
    (re.compile(r"\bslices?\b", re.I), "slice"),
    (re.compile(r"\bsticks?\b", re.I), "stick"),
    (re.compile(r"\bpackages?\b|\bpkg\.?\b", re.I), "package"),
    (re.compile(r"\bservings?\b", re.I), "serving"),
    (re.compile(r"\bcloves?\b", re.I), "clove"),
    (re.compile(r"\bsprigs?\b", re.I), "sprig"),
    (re.compile(r"\bbunch(?:es)?\b", re.I), "bunch"),
    (re.compile(r"\bcans?\b", re.I), "can"),
    (re.compile(r"\bbottles?\b", re.I), "bottle"),
    (re.compile(r"\bjars?\b", re.I), "jar"),
    (re.compile(r"\bheads?\b", re.I), "head"),
    (re.compile(r"\bears?\b", re.I), "ear"),
    (re.compile(r"\bstalks?\b", re.I), "stalk"),
    (re.compile(r"\bleaves?\b", re.I), "leaf"),
]

# Match (digit-or-fraction-or-mixed-number)
QTY_RE = re.compile(
    r"(?P<whole>\d+)?\s*"
    r"(?P<frac>\d+\s*/\s*\d+)?"
    r"(?P<dec>\.\d+)?"
)


def _replace_unicode_fractions(s: str) -> str:
    out = s
    for slash in ("⁄", "∕", "／"):
        out = out.replace(slash, "/")
    for k, v in UNI_FRAC.items():
        out = out.replace(k, " " + v + " ")
    return out


def parse_qty(token_str: str) -> float | None:
    """Parse a leading quantity token: '1', '1/2', '1 1/2', '0.5', '½'.

    Order matters: try mixed number ("1 1/2") first, then bare fraction
    ("1/4"), then decimal ("0.5" / "1.5"), then plain whole ("3"). The naive
    `\\d+(\\d+/\\d+)?` regex eats the leading digit and misses the fraction,
    making "1/4" parse as 1.0.
    """
    if not token_str:
        return None
    s = _replace_unicode_fractions(token_str.strip())

    # 1. mixed number: "1 1/2"
    m = re.match(r"^\s*(\d+)\s+(\d+)\s*/\s*(\d+)\b", s)
    if m:
        whole, num, den = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if den:
            return whole + num / den

    # 2. bare fraction: "1/4"
    m = re.match(r"^\s*(\d+)\s*/\s*(\d+)\b", s)
    if m:
        num, den = int(m.group(1)), int(m.group(2))
        if den:
            return num / den

    # 3. decimal: "0.5", "1.5", ".5"
    m = re.match(r"^\s*(\d*\.\d+)\b", s)
    if m:
        return float(m.group(1))

    # 4. plain whole: "3"
    m = re.match(r"^\s*(\d+)\b", s)
    if m:
        return float(m.group(1))

    return None


def normalize_unit(token: str) -> str | None:
    if not token:
        return None
    for pat, name in UNIT_NORM:
        if pat.search(token):
            return name
    return None


def extract_qty_unit(display: str) -> tuple[float | None, str | None, str]:
    """Pull qty + unit from a display string.

    Returns (qty, unit, residual) where residual is the rest of the string
    after stripping qty + unit.

    Handles common recipe shapes:
      "1 1/2 cups sugar"
      "1/4 cup butter"
      "5-6 lb ham"                  → midpoint 5.5 lb
      "1 (5-6 pound) bone-in ham"   → 5.5 lb (unwrap parenthetical)
      "1 (15 oz) can tomatoes"      → 15 oz
      "5 to 6 lbs ham"              → midpoint 5.5 lb
    """
    if not display:
        return None, None, ""
    s = _replace_unicode_fractions(display).strip()

    # Special case: "N (X-Y unit) ..." or "N (X unit) ..." — recipe writers
    # wrap the WEIGHT in parens and prefix a count of "1". The weight is
    # the useful number; the leading "1" is a count we discard.
    paren_m = re.match(
        r"^\s*\d+\s*\(\s*"
        r"(?P<lo>\d+(?:\.\d+)?)\s*(?:[-–to]+\s*(?P<hi>\d+(?:\.\d+)?))?"
        r"\s*(?P<unit>[A-Za-z\.]+(?:\s+[A-Za-z\.]+)?)\s*\)",
        s,
    )
    if paren_m:
        lo = float(paren_m.group("lo"))
        hi = float(paren_m.group("hi")) if paren_m.group("hi") else lo
        qty = (lo + hi) / 2
        unit = normalize_unit(paren_m.group("unit"))
        rest = s[paren_m.end():].strip(", ")
        return qty, unit, rest

    # Range without parens: "5-6 lb ham" or "5 to 6 lbs ham"
    range_m = re.match(
        r"^\s*(?P<lo>\d+(?:\.\d+)?)\s*(?:[-–]|to)\s*(?P<hi>\d+(?:\.\d+)?)\s*"
        r"(?P<unit>[A-Za-z\.]+)?",
        s,
    )
    if range_m and range_m.group("hi"):
        lo = float(range_m.group("lo"))
        hi = float(range_m.group("hi"))
        qty = (lo + hi) / 2
        unit_tok = range_m.group("unit") or ""
        unit = normalize_unit(unit_tok)
        rest = s[range_m.end():].strip(", ")
        return qty, unit, rest

    # leading quantity: try the patterns in priority order so "1/4" doesn't
    # parse as 1.0 (the naive single-regex approach loses the fraction).
    qty: float | None = None
    qty_end = 0
    for pat in (
        r"^\s*(\d+\s+\d+\s*/\s*\d+)",       # mixed: "1 1/2"
        r"^\s*(\d+\s*/\s*\d+)",              # bare fraction: "1/4"
        r"^\s*(\d*\.\d+)",                   # decimal: "0.5", ".25"
        r"^\s*(\d+)",                        # whole: "3"
    ):
        m = re.match(pat, s)
        if m:
            qty = parse_qty(m.group(1))
            qty_end = m.end()
            break
    rest = s[qty_end:] if qty_end else s

    # unit token (first word after qty, but allow "fl oz")
    # try a 2-word unit first
    unit = None
    m2 = re.match(r"^\s*([a-zA-Z.]+(?:\s+[a-zA-Z.]+)?)\b", rest)
    if m2:
        candidate = m2.group(1).strip()
        unit = normalize_unit(candidate)
        if unit:
            rest = rest[m2.end():].strip()
        else:
            # try single word
            m1 = re.match(r"^\s*([a-zA-Z.]+)\b", rest)
            if m1:
                unit = normalize_unit(m1.group(1))
                if unit:
                    rest = rest[m1.end():].strip()
    rest = rest.strip(", ")
    return qty, unit, rest


__all__ = ["extract_qty_unit", "parse_qty", "normalize_unit"]
