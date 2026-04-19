"""
Empreinte phonétique simplifiée (Metaphone-like) — utilisée en dernier recours
quand Levenshtein et Jaro-Winkler échouent tous les deux.

Intuition : deux mots qui "sonnent pareil" partagent la même empreinte, même
lorsque leur distance d'édition est élevée (ex. 'projecteur' vs 'projeckteur',
'videoprojecteur' vs 'vidioprojectere').

Règles :
  1. On garde la première lettre intacte (capture l'"attaque" du mot).
  2. On remplace les groupes de consonnes homophones :
        c, k, q, ck        → c      (sons 'k')
        z, s, x (initial)  → s      (sifflantes)
        ph, f              → f
        y, i               → i
        w                  → v
  3. On supprime toutes les voyelles sauf la première.
  4. On compresse les lettres identiques consécutives.

Ne remplace pas un vrai Metaphone/Soundex, mais fonctionne très bien pour des
noms techniques courts (types d'équipement, marques) rencontrés dans SmartFind.
"""

from __future__ import annotations

import re

_PHONETIC_REPLACEMENTS = [
    (re.compile(r"ph"), "f"),
    (re.compile(r"ck"), "c"),
    (re.compile(r"ch"), "c"),
    (re.compile(r"sh"), "s"),
    (re.compile(r"th"), "t"),
    (re.compile(r"qu"), "c"),
]

_CHAR_MAP = str.maketrans({
    "k": "c",
    "q": "c",
    "x": "c",
    "z": "s",
    "y": "i",
    "w": "v",
    "-": "",
    "_": "",
})

_VOWELS = set("aeiouh")
_ALPHA_ONLY = re.compile(r"[^a-z]")


def phonetic_key(term: str) -> str:
    """
    Renvoie une clé phonétique minuscule pour ``term``.
    Deux mots avec la même clé "sonnent" approximativement pareil.

    >>> phonetic_key("projecteur") == phonetic_key("projeckteur")
    True
    >>> phonetic_key("scanner") == phonetic_key("skanner")
    True
    >>> phonetic_key("imprimante") == phonetic_key("pizza")
    False
    """
    if not term:
        return ""

    t = term.lower()
    for pattern, replacement in _PHONETIC_REPLACEMENTS:
        t = pattern.sub(replacement, t)
    t = t.translate(_CHAR_MAP)
    t = _ALPHA_ONLY.sub("", t)
    if not t:
        return ""

    head = t[0]
    rest = "".join(c for c in t[1:] if c not in _VOWELS)

    # Compression des lettres identiques consécutives
    compressed = head
    for c in rest:
        if compressed[-1] != c:
            compressed += c

    return compressed


def phonetic_match(a: str, b: str) -> bool:
    """True si ``a`` et ``b`` partagent la même empreinte phonétique."""
    key_a = phonetic_key(a)
    key_b = phonetic_key(b)
    return bool(key_a) and key_a == key_b
