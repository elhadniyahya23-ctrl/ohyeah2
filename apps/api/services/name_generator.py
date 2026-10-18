from __future__ import annotations

import itertools
import string
from pathlib import Path

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
# Letters, digits, underscore — valid on MC / Discord. Dots use dedicated generators.
CHARS = string.ascii_lowercase + string.digits + "_"
PREVIEW_LIMIT = 1000  # exported for names router count endpoint
MAX_STACK_LAYERS = 10

HEAVY_TYPES = frozenset({"4L", "4C", "EXCEPT4L", "SEMI3L", "COMBO3", "3C"})

WORD_LISTS: dict[str, dict[str, str | int]] = {
    "TOP10K": {"file": "top_english_words.txt", "lang": "en", "count": 10000},
    "TOP20K": {"file": "top_20k_words.txt", "lang": "en", "count": 20000},
    "TOP30K": {"file": "top_30k_words.txt", "lang": "en", "count": 30000},
    "TOP100K": {"file": "top_100k_words.txt", "lang": "en", "count": 100000},
    "TOP10K_FR": {"file": "top_10k_french.txt", "lang": "fr", "count": 10000},
    "TOP30K_FR": {"file": "top_30k_french.txt", "lang": "fr", "count": 30000},
    "TOP10K_EN_5L": {"file": "top_10k_en_5l.txt", "lang": "en", "count": 10000},
    "TOP10K_FR_5L": {"file": "top_10k_fr_5l.txt", "lang": "fr", "count": 10000},
    "4L_PRONOUNCE": {"file": "4l_pronounceable.txt", "lang": "none"},
    "5L_PRONOUNCE": {"file": "5l_pronounceable.txt", "lang": "none"},
    "FACES": {"file": "faces.txt", "lang": "none"},
    "4L_REPEATERS": {"file": "4l_repeaters.txt", "lang": "none"},
    "EGIRL_500": {"file": "egirl_names.txt", "lang": "none"},
    "EBOY_500": {"file": "eboy_names.txt", "lang": "none"},
    "4C_LEET": {"file": "4c_leet_words.txt", "lang": "none"},
    "CITIES_FR": {"file": "cities_fr.txt", "lang": "none"},
    "SEMI3L_DOT_500": {"file": "semi_3l_dot_500.txt", "lang": "none"},
    "DOTTED_WORDS_7L": {"file": "dotted_words_7l.txt", "lang": "none"},
}


class NameGenError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def _resolve_word_list_path(filename: str) -> Path:
    return RESOURCES_DIR / filename


def _read_word_file(filename: str) -> list[str]:
    path = _resolve_word_list_path(filename)
    if not path.is_file():
        raise NameGenError(f"{filename} not found in resources/")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _generate_except4l_combos(chars: str) -> list[str]:
    pure_4l = set(itertools.product(string.ascii_lowercase, repeat=4))
    combos: list[str] = []
    combos.extend("".join(x) for x in itertools.product(chars, repeat=2))
    combos.extend("".join(x) for x in itertools.product(chars, repeat=3))
    for x in itertools.product(chars, repeat=4):
        if x in pure_4l:
            continue
        combos.append("".join(x))
    for c1 in string.ascii_lowercase:
        for c2 in string.ascii_lowercase:
            for c3 in string.ascii_lowercase:
                combos.append(f"{c1}_{c2}{c3}")
                combos.append(f"{c1}{c2}_{c3}")
    return combos


def _generate_semi3l_dot_500() -> list[str]:
    combos: list[str] = []
    for c1 in string.ascii_lowercase:
        for c2 in string.ascii_lowercase:
            for c3 in string.ascii_lowercase:
                combos.append(f"{c1}.{c2}{c3}")
                if len(combos) >= 500:
                    return combos
    return combos


def _generate_dotted_words_7l() -> list[str]:
    combos: list[str] = []
    for word in _read_word_file("top_english_words.txt"):
        w = word.lower().strip()
        if len(w) == 7 and w.isalpha():
            combos.append(".".join(w))
    return combos


def _generate_eboy_500() -> list[str]:
    base = [
        "shadow", "phantom", "nova", "zero", "ghost", "blaze", "storm", "venom",
        "onyx", "raven", "cipher", "drift", "frost", "hex", "kairo", "lynx",
        "myth", "neo", "orion", "pulse", "riot", "sage", "titan", "vex",
        "wolf", "xen", "yuki", "zen", "ace", "blade", "core", "dark",
    ]
    combos: list[str] = []
    for name in base:
        combos.append(name)
        combos.append(f"{name}x")
        combos.append(f"x{name}")
        combos.append(f"{name}_")
        if len(combos) >= 500:
            break
    while len(combos) < 500:
        combos.append(f"boy{len(combos)}")
    return combos[:500]


def _generate_cities_fr() -> list[str]:
    cities = [
        "paris", "marseille", "lyon", "toulouse", "nice", "nantes", "montpellier",
        "strasbourg", "bordeaux", "lille", "rennes", "reims", "toulon", "grenoble",
        "dijon", "angers", "nimes", "villeurbanne", "clermont", "lehavre", "saintetienne",
        "toulon", "tours", "amiens", "limoges", "perpignan", "metz", "besancon",
        "orleans", "rouen", "mulhouse", "caen", "nancy", "argenteuil", "montreuil",
        "roubaix", "tourcoing", "avignon", "dunkerque", "poitiers", "versailles",
    ]
    combos = list(dict.fromkeys(cities))
    i = 0
    while len(combos) < 1500:
        combos.append(f"ville{i}")
        i += 1
    return combos[:1500]


def _generate_4c_leet() -> list[str]:
    leet_map = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"}
    combos: list[str] = []
    for word in _read_word_file("top_english_words.txt"):
        w = word.lower().strip()
        if not (3 <= len(w) <= 4 and w.isalpha()):
            continue
        variant = "".join(leet_map.get(c, c) for c in w)
        if variant != w:
            combos.append(variant)
        if len(combos) >= 5000:
            break
    return combos


def _generate_letter_repeaters(chars: str, max_len: int = 32) -> list[str]:
    combos: list[str] = []
    for c in chars:
        for n in range(1, max_len + 1):
            combos.append(c * n)
    return combos


def generate_names(gen_type: str, *, include_verbs: bool = True) -> list[str]:
    gen_type = gen_type.strip().upper()
    chars = CHARS

    if gen_type in WORD_LISTS:
        info = WORD_LISTS[gen_type]
        filename = str(info["file"])

        if gen_type == "SEMI3L_DOT_500":
            path = _resolve_word_list_path(filename)
            return _read_word_file(filename) if path.is_file() else _generate_semi3l_dot_500()
        if gen_type == "DOTTED_WORDS_7L":
            path = _resolve_word_list_path(filename)
            return _read_word_file(filename) if path.is_file() else _generate_dotted_words_7l()
        if gen_type == "EBOY_500":
            path = _resolve_word_list_path(filename)
            return _read_word_file(filename) if path.is_file() else _generate_eboy_500()
        if gen_type == "CITIES_FR":
            path = _resolve_word_list_path(filename)
            return _read_word_file(filename) if path.is_file() else _generate_cities_fr()
        if gen_type == "4C_LEET":
            path = _resolve_word_list_path(filename)
            return _read_word_file(filename) if path.is_file() else _generate_4c_leet()

        if not include_verbs and info.get("lang") in ("en", "fr") and "count" in info:
            verb_file = RESOURCES_DIR / f"{info['lang']}_verbs.txt"
            verbs: set[str] = set()
            if verb_file.is_file():
                verbs = {v.strip().lower() for v in verb_file.read_text(encoding="utf-8").splitlines() if v.strip()}
            source_name = "top_100k_words.txt" if info["lang"] == "en" else "top_30k_french.txt"
            source = _read_word_file(source_name)
            combos: list[str] = []
            for w in source:
                if w.lower() not in verbs:
                    combos.append(w)
                if len(combos) >= int(info["count"]):
                    break
            return combos

        return _read_word_file(filename)

    if gen_type == "UNDERSCORE_RPT":
        return [f"{c}_{c}" for c in chars] + [f"{c}__{c}" for c in chars]
    if gen_type == "LETTER_RPT":
        return _generate_letter_repeaters(chars, 32)
    if gen_type == "2C":
        return ["".join(x) for x in itertools.product(chars, repeat=2)]
    if gen_type == "2L":
        return ["".join(x) for x in itertools.product(string.ascii_lowercase, repeat=2)]
    if gen_type == "2N":
        return ["".join(x) for x in itertools.product(string.digits, repeat=2)]
    if gen_type == "3C":
        return ["".join(x) for x in itertools.product(chars, repeat=3)]
    if gen_type == "3L":
        return ["".join(x) for x in itertools.product(string.ascii_lowercase, repeat=3)]
    if gen_type == "3N":
        return ["".join(x) for x in itertools.product(string.digits, repeat=3)]
    if gen_type == "4N":
        return ["".join(x) for x in itertools.product(string.digits, repeat=4)]
    if gen_type == "4L":
        return ["".join(x) for x in itertools.product(string.ascii_lowercase, repeat=4)]
    if gen_type == "4C":
        return ["".join(x) for x in itertools.product(chars, repeat=4)]
    if gen_type == "COMBO2":
        return generate_names("2C", include_verbs=include_verbs)
    if gen_type == "COMBO3":
        return generate_names("3C", include_verbs=include_verbs)
    if gen_type == "SEMI3L":
        combos = []
        for c1 in string.ascii_lowercase:
            for c2 in string.ascii_lowercase:
                for c3 in string.ascii_lowercase:
                    combos.append(f"{c1}_{c2}{c3}")
                    combos.append(f"{c1}{c2}_{c3}")
        return combos
    if gen_type == "EXCEPT4L":
        return _generate_except4l_combos(chars)

    raise NameGenError("Invalid generator type")


def merge_names(existing: list[str], new: list[str], *, append: bool) -> list[str]:
    if append:
        # Newest batch first so the textarea preview shows the just-added list.
        return list(dict.fromkeys([*new, *existing]))
    return list(dict.fromkeys(new))


def names_preview(names: list[str], *, stack_count: int = 0) -> dict:
    is_large = len(names) > PREVIEW_LIMIT
    preview = names[:PREVIEW_LIMIT] if is_large else names
    content = "\n".join(preview)
    if is_large:
        content += f"\n... and {len(names) - PREVIEW_LIMIT} more (Preview limited to {PREVIEW_LIMIT})"
    return {
        "content": content,
        "is_large": is_large,
        "count": len(names),
        "stack_count": max(0, int(stack_count)),
        "stack_limit": MAX_STACK_LAYERS,
    }
