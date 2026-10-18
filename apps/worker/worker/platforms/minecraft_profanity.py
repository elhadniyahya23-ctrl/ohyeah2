"""Minecraft insult / abbreviation filter (EN + FR).

Sources consulted:
- fr.wikipedia.org Liste de termes d'argot Internet
- fr.wiktionary.org Annexe:Liste de termes d'argot Internet
- cyberbullying.org Chat/Text Abbreviations
- stronglang.wordpress.com sweary abbreviations
- vidalingua.com French internet slang

Ambiguous tokens that are also common non-insult handles (ftw, tgv, pita, osef,
mdr, lmao, cul8r, …) are intentionally omitted.
"""

from __future__ import annotations

import re

_MC_NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
_TRAILING_DIGITS_RE = re.compile(r"\d+$")
_LEET_TABLE = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "8": "b",
        "@": "a",
        "$": "s",
    }
)

# Full insults + abbreviations (exact / bare / deleet match).
_MC_INSULTS_EXACT = frozenset(
    {
        # --- English insults ---
        "anal",
        "anus",
        "arse",
        "ass",
        "asshole",
        "bastard",
        "bitch",
        "biatch",
        "blowjob",
        "bollocks",
        "boob",
        "boobs",
        "cock",
        "cocks",
        "coon",
        "cunt",
        "cum",
        "dick",
        "dicks",
        "dildo",
        "dyke",
        "fag",
        "faggot",
        "fags",
        "fuck",
        "fuckboy",
        "fucker",
        "fuckers",
        "fucking",
        "fucks",
        "gayass",
        "handjob",
        "homo",
        "hooker",
        "horny",
        "jizz",
        "kike",
        "milf",
        "molest",
        "motherfucker",
        "nazi",
        "negro",
        "nig",
        "niga",
        "nigga",
        "nigger",
        "niggers",
        "nude",
        "nudes",
        "orgasm",
        "pedo",
        "pedophile",
        "penis",
        "piss",
        "porn",
        "porno",
        "pussy",
        "queer",
        "rape",
        "rapist",
        "retard",
        "retarded",
        "sex",
        "sexy",
        "shit",
        "shits",
        "slut",
        "sluts",
        "spic",
        "tit",
        "tits",
        "tranny",
        "twat",
        "vagina",
        "wank",
        "whore",
        # --- English abbreviations / spellings ---
        "asafp",
        "azz",
        "bamf",
        "bde",
        "bfd",
        "bffr",
        "btch",
        "cyaa",
        "dafuq",
        "dilligaf",
        "dtf",
        "fafo",
        "fboi",
        "fck",
        "fcker",
        "fcking",
        "fcku",
        "ffs",
        "fkuc",
        "fml",
        "fubar",
        "fuk",
        "fuker",
        "fvck",
        "fyfi",
        "fyvm",
        "gdmf",
        "gtfo",
        "hgs",
        "idgaf",
        "jfgi",
        "kms",
        "kys",
        "lmp",
        "mf",
        "mfer",
        "mfkr",
        "mofo",
        "nfg",
        "nfw",
        "nsfl",
        "nsfw",
        "omfg",
        "phuck",
        "pos",
        "rtfm",
        "sfa",
        "sht",
        "shyt",
        "smfh",
        "snafu",
        "sob",
        "stfu",
        "stfw",
        "suff",
        "thot",
        "wap",
        "wtaf",
        "wtf",
        "wtfo",
        # --- French insults ---
        "bite",
        "connard",
        "connasse",
        "couille",
        "couilles",
        "encule",
        "enculer",
        "merde",
        "nique",
        "niquer",
        "petasse",
        "pute",
        "putain",
        "salope",
        "salaud",
        "tamere",
        "tagueule",
        "trouduc",
        "trou_du_cul",
        # --- French abbreviations (argot internet / SMS) ---
        "balek",
        "blc",
        "cmb",
        "ctb",
        "dmc",
        "dsc",
        "dtc",
        "fdg",
        "fdp",
        "fdpute",
        "fpc",
        "ftg",
        "mbab",
        "ntm",
        "ntmr",
        "ntmsm",
        "pdm",
        "pt1",
        "ptn",
        "put1",
        "rab",
        "raf",
        "spc",
        "spcdd",
        "tdc",
        "tg",
        "tgl",
        "tmlp",
        "vtf",
        "vtfe",
        "vtff",
        "vtm",
    }
)

# 2–3 char abbrevs: whole name or abbrev+digits only (never substring).
_MC_SHORT_ABBREVS = frozenset(
    {
        "af",
        "azz",
        "bde",
        "bfd",
        "blc",
        "cmb",
        "ctb",
        "dmc",
        "dsc",
        "dtc",
        "dtf",
        "fafo",
        "fck",
        "fdp",
        "ffs",
        "fk",
        "fml",
        "fpc",
        "ftg",
        "fu",
        "fuk",
        "fy",
        "gtfo",
        "kys",
        "kms",
        "mf",
        "nfg",
        "nfw",
        "nig",
        "ntm",
        "pd",
        "pdm",
        "pos",
        "pt1",
        "ptn",
        "put1",
        "rab",
        "raf",
        "sht",
        "sob",
        "spc",
        "tdc",
        "tf",
        "tg",
        "tgl",
        "vtf",
        "vtm",
        "wap",
        "wtf",
    }
)

# Strong substrings only (avoid unique/computer/torpedo/grape false positives).
_MC_INSULT_SUBSTRING_BLOCK = frozenset(
    {
        "asshole",
        "bastard",
        "biatch",
        "bitch",
        "blowjob",
        "bollocks",
        "dildo",
        "faggot",
        "fuck",
        "fuckboy",
        "fucker",
        "fuckers",
        "fucking",
        "handjob",
        "motherfucker",
        "nigger",
        "nigga",
        "niggers",
        "pedophile",
        "penis",
        "pussy",
        "rapist",
        "retard",
        "retarded",
        "shit",
        "tranny",
        "vagina",
        "whore",
        "connard",
        "connasse",
        "couille",
        "couilles",
        "encule",
        "enculer",
        "putain",
        "salope",
        "salaud",
        "petasse",
        "trouduc",
        "tamere",
        "tagueule",
        "fdpute",
        "tmlp",
        "vtfe",
        "vtff",
    }
)


def _deleet(value: str) -> str:
    return value.translate(_LEET_TABLE)


def _tokens_to_check(name: str) -> set[str]:
    lower = name.lower()
    compact = lower.replace("_", "")
    bare = _TRAILING_DIGITS_RE.sub("", compact) or compact
    return {t for t in (lower, compact, bare, _deleet(compact), _deleet(bare)) if t}


def _matches_short_abbrev(compact: str) -> bool:
    for ab in _MC_SHORT_ABBREVS:
        if compact == ab:
            return True
        if compact.startswith(ab) and compact[len(ab) :].isdigit() and compact[len(ab) :]:
            return True
    return False


def minecraft_inappropriate_reason(name: str) -> str | None:
    """Return a detail if the name cannot be claimed (format or insult filter)."""
    raw = (name or "").strip()
    if not raw or not _MC_NAME_RE.fullmatch(raw):
        return "invalid"
    # Mojang min length is 3; 1–2 char handles are legacy-only and unclaimable.
    if len(raw) < 3:
        return "invalid"

    tokens = _tokens_to_check(raw)
    if tokens & _MC_INSULTS_EXACT:
        return "inappropriate"

    compact = raw.lower().replace("_", "")
    if _matches_short_abbrev(compact) or _matches_short_abbrev(_deleet(compact)):
        return "inappropriate"

    haystacks = {compact, _deleet(compact)}
    for word in _MC_INSULT_SUBSTRING_BLOCK:
        for hay in haystacks:
            if word in hay:
                return "inappropriate"
    return None
