"""Controlled cheese identity aliases shared by HTC registry/taggers.

The retail tree already carries many cheese varieties as path segments,
modifiers, FNDDS descriptions, or SR-28 descriptions even when
``product_identity_fixed`` stayed at generic ``Cheese``.  These helpers promote
those audited taxonomy signals into stable food identities before HTC encoding.
"""
from __future__ import annotations

import re
import unicodedata


TOKEN_RE = re.compile(r"[a-z0-9]+")


def _plain(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(TOKEN_RE.findall(folded.lower()))


# Canonical identity -> aliases.  Multi-word aliases are deliberately broad:
# these are taxonomy identities, not marketing keywords, and are applied only
# in cheese context or when the source text itself says cheese.
CHEESE_IDENTITY_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Parmigiano Reggiano", ("parmigiano reggiano", "parmigiano-reggiano", "parmigiano", "reggiano")),
    ("Grana Padano", ("grana padano",)),
    ("Pecorino Romano", ("pecorino romano",)),
    ("Colby Jack", ("colby jack", "colby-jack", "colby monterey jack", "colby and monterey jack", "monterey jack colby", "monterey jack and colby")),
    ("Colby", ("american style colby", "american-style colby", "colby",)),
    ("Cheddar Jack", ("cheddar jack", "cheddar and monterey jack", "cheddar monterey jack")),
    ("Pepper Jack", ("pepper jack", "pepperjack", "jalapeno jack", "jalapeno monterey jack")),
    ("Mexican Blend Cheese", ("mexican blend", "mexican cheese blend", "mexican style blend", "mexican style cheese", "mexican style four cheese", "mexican style 4 cheese", "four cheese mexican", "4 cheese mexican", "3 cheese mexican", "mexican four cheese", "mexican 4 cheese")),
    ("Italian Blend Cheese", ("italian blend", "italian cheese blend", "italian style blend", "italian style cheese")),
    ("Taco Cheese", ("taco cheese", "taco cheese blend", "seasoned taco blend", "nacho taco")),
    ("American Cheese", ("american cheese", "american style", "american-style")),
    ("Velveeta Cheese", ("velveeta",)),
    ("Cream Cheese", ("cream cheese",)),
    ("Cottage Cheese", ("cottage cheese",)),
    ("Goat Cheese", ("goat cheese", "chevre", "chevre cheese")),
    ("Blue Cheese", ("blue cheese", "bleu cheese")),
    ("String Cheese", ("string cheese",)),
    ("Monterey Jack", ("monterey jack", "monterey")),
    ("Mozzarella", ("mozzarella",)),
    ("Cheddar", ("cheddar",)),
    ("Parmesan", ("parmesan",)),
    ("Provolone", ("provolone",)),
    ("Feta", ("feta",)),
    ("Ricotta", ("ricotta",)),
    ("Swiss", ("swiss cheese", "baby swiss", "swiss")),
    ("Gouda", ("gouda",)),
    ("Asiago", ("asiago",)),
    ("Brie", ("brie",)),
    ("Havarti", ("havarti",)),
    ("Romano", ("romano",)),
    ("Burrata", ("burrata",)),
    ("Manchego", ("manchego",)),
    ("Muenster", ("muenster", "munster")),
    ("Mascarpone", ("mascarpone",)),
    ("Halloumi", ("halloumi",)),
    ("Limburger", ("limburger",)),
    ("Pecorino", ("pecorino",)),
    ("Stilton", ("stilton",)),
    ("Cotija", ("cotija",)),
    ("Paneer", ("paneer",)),
    ("Brick", ("brick cheese",)),
    ("Edam", ("edam",)),
    ("Bocconcini", ("bocconcini",)),
    ("Boursin", ("boursin",)),
    ("Fontina", ("fontina",)),
    ("Roquefort", ("roquefort",)),
    ("Tilsit", ("tilsit",)),
    ("Gorgonzola", ("gorgonzola",)),
    ("Gruyere", ("gruyere", "gruyere cheese", "gruyère", "gruyère cheese")),
    ("Jarlsberg", ("jarlsberg",)),
    ("Emmentaler", ("emmentaler", "emmenthaler", "emmental")),
    ("Raclette", ("raclette",)),
    ("Taleggio", ("taleggio",)),
    ("Wensleydale", ("wensleydale",)),
    ("Caciocavallo", ("caciocavallo",)),
    ("Gloucester", ("gloucester",)),
    ("Quark", ("quark",)),
    ("Tomme", ("tomme",)),
    ("Camembert", ("camembert",)),
    ("Farmer Cheese", ("farmer cheese", "farmers cheese")),
    ("Longhorn", ("longhorn",)),
    ("Asadero", ("asadero",)),
    ("Queso Quesadilla", ("queso quesadilla",)),
    ("Oaxaca", ("oaxaca",)),
    ("Chihuahua", ("chihuahua cheese", "queso chihuahua")),
    ("Panela", ("panela",)),
    ("Kasseri", ("kasseri",)),
    ("Mizithra", ("mizithra", "myzithra")),
    ("Neufchatel", ("neufchatel", "neufchâtel")),
    ("Yogurt Cheese", ("yogurt cheese", "yoghurt cheese")),
)


def _alias_rows() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for canonical, aliases in CHEESE_IDENTITY_ALIASES:
        rows.append((_plain(canonical), canonical))
        for alias in aliases:
            rows.append((_plain(alias), canonical))
    rows = [(alias, canonical) for alias, canonical in rows if alias]
    rows.sort(key=lambda item: (len(item[0].split()), len(item[0])), reverse=True)
    return rows


ALIAS_TO_CANONICAL = _alias_rows()


def cheese_identity_from_text(value: str) -> str:
    """Return a canonical cheese identity if the text names one."""
    norm = _plain(value)
    if not norm:
        return ""
    haystack = f" {norm} "
    best: tuple[int, int, str] | None = None
    for alias, canonical in ALIAS_TO_CANONICAL:
        needle = f" {alias} "
        pos = haystack.find(needle)
        if pos < 0:
            continue
        candidate = (pos, -len(alias.split()), canonical)
        if best is None or candidate < best:
            best = candidate
    return best[2] if best else ""


def cheese_registry_names() -> list[str]:
    """Canonical cheese identities that should have stable food slots."""
    out: list[str] = []
    seen: set[str] = set()
    for canonical, _aliases in CHEESE_IDENTITY_ALIASES:
        if canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out
