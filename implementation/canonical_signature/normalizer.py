from __future__ import annotations
import re
import unicodedata

_ABBREVS = {
    # Patterns ending in a non-word char (. or /) cannot use \b after that char
    # because \b requires an adjacent \w character. Use negative lookaround instead.
    r"(?<!\w)org\.(?!\w)": "organic",
    r"(?<!\w)w/(?!\w)": "with",
    r"(?<!\w)w/o(?!\w)": "without",
    r"\bnatl\b": "natural",
    r"\bchoc\b": "chocolate",
    r"\bveg\b": "vegetable",
}

_AMP_BETWEEN_WORDS = re.compile(r"(?<=[a-z]{2})\s*&\s*(?=[a-z]{2})")
_PUNCT_TO_DROP = re.compile(r"['.,;:!?()\[\]\"]")
_COMMA_NORMALIZE = re.compile(r"\s*,\s*")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    if text is None:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = _COMMA_NORMALIZE.sub("§COMMA§", text)
    # Expand abbreviations before stripping punctuation so patterns like
    # \borg\.\b and \bw/\b can match while their punctuation is still present.
    for pattern, repl in _ABBREVS.items():
        text = re.sub(pattern, repl, text)
    text = _PUNCT_TO_DROP.sub("", text)
    text = _AMP_BETWEEN_WORDS.sub(" and ", text)
    text = text.replace("§COMMA§", ", ")
    text = _WS.sub(" ", text).strip()
    return text
