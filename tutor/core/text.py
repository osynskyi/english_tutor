"""Text normalization shared by answer checking, dictation and speech scoring.

Speech recognizers and learners write the same sentence in different ways
("I'm" / "I am", "7" / "seven", "colour" / "color"), so everything is reduced
to a canonical list of lowercase words before comparing.
"""

from __future__ import annotations

import re

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'", "ʼ": "'"})
_DASHES = re.compile(r"[-‐‑‒–—―/]")
_NON_WORD = re.compile(r"[^a-z0-9' ]+")

CONTRACTIONS: dict[str, str] = {
    "i'm": "i am",
    "you're": "you are",
    "we're": "we are",
    "they're": "they are",
    "he's": "he is",
    "she's": "she is",
    "it's": "it is",
    "that's": "that is",
    "there's": "there is",
    "here's": "here is",
    "what's": "what is",
    "where's": "where is",
    "who's": "who is",
    "how's": "how is",
    "when's": "when is",
    "let's": "let us",
    "i've": "i have",
    "you've": "you have",
    "we've": "we have",
    "they've": "they have",
    "i'll": "i will",
    "you'll": "you will",
    "he'll": "he will",
    "she'll": "she will",
    "it'll": "it will",
    "we'll": "we will",
    "they'll": "they will",
    "that'll": "that will",
    "i'd": "i would",
    "you'd": "you would",
    "he'd": "he would",
    "she'd": "she would",
    "we'd": "we would",
    "they'd": "they would",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "haven't": "have not",
    "hasn't": "has not",
    "hadn't": "had not",
    "won't": "will not",
    "wouldn't": "would not",
    "can't": "can not",
    "cannot": "can not",
    "couldn't": "could not",
    "shouldn't": "should not",
    "mustn't": "must not",
    "needn't": "need not",
    "shan't": "shall not",
    "y'all": "you all",
    "gonna": "going to",
    "wanna": "want to",
    "gotta": "got to",
}

# Speech recognizers default to American spelling.
SPELLING: dict[str, str] = {
    "colour": "color",
    "colours": "colors",
    "favourite": "favorite",
    "favourites": "favorites",
    "centre": "center",
    "theatre": "theater",
    "metre": "meter",
    "metres": "meters",
    "travelling": "traveling",
    "travelled": "traveled",
    "cancelled": "canceled",
    "organise": "organize",
    "organised": "organized",
    "realise": "realize",
    "realised": "realized",
    "apologise": "apologize",
    "neighbour": "neighbor",
    "neighbours": "neighbors",
    "honour": "honor",
    "humour": "humor",
    "flavour": "flavor",
    "behaviour": "behavior",
    "grey": "gray",
    "programme": "program",
    "cheque": "check",
    "jewellery": "jewelry",
    "ok": "okay",
}

_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def number_to_words(n: int) -> str:
    """Spell out 0..999999 in words ("125" -> "one hundred twenty five")."""
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return f"{_ONES[hundreds]} hundred" + (f" {number_to_words(rest)}" if rest else "")
    if n < 1_000_000:
        thousands, rest = divmod(n, 1000)
        return f"{number_to_words(thousands)} thousand" + (f" {number_to_words(rest)}" if rest else "")
    return str(n)


def _expand_token(token: str) -> list[str]:
    token = token.strip("'")
    if not token:
        return []
    if token in CONTRACTIONS:
        return CONTRACTIONS[token].split()
    if token in SPELLING:
        return [SPELLING[token]]
    if token.isdigit():
        return number_to_words(int(token)).split()
    # 25th, 3rd, 1990s -> keep the number part readable
    match = re.fullmatch(r"(\d+)(st|nd|rd|th|s)", token)
    if match:
        return number_to_words(int(match.group(1))).split() + [match.group(2)]
    return [token]


def split_words(text: str) -> list[str]:
    """Lowercase and split into raw word tokens (no expansion)."""
    text = text.lower().translate(_APOSTROPHES)
    text = text.replace("o'clock", "oclock")
    text = re.sub(r"(\d):(\d\d)", r"\1 \2", text)  # 7:30 -> 7 30
    text = _DASHES.sub(" ", text)
    text = _NON_WORD.sub(" ", text)
    return [t for t in text.split() if t.strip("'")]


def normalize_words(text: str) -> list[str]:
    """Canonical word list used for every comparison."""
    words: list[str] = []
    for token in split_words(text):
        words.extend(_expand_token(token))
    return words


def normalize(text: str) -> str:
    return " ".join(normalize_words(text))


def word_forms(word: str) -> set[str]:
    """The word plus its possible singular forms, so "coffees" matches "coffee"."""
    forms = {word}
    if len(word) > 3:
        if word.endswith("ies"):
            forms.add(word[:-3] + "y")
        if word.endswith("es"):
            forms.add(word[:-2])
        if word.endswith("s"):
            forms.add(word[:-1])
    return forms


def words_match(a: str, b: str) -> bool:
    return bool(word_forms(a) & word_forms(b))
