"""Menswear vocabulary shared by the fallback parser and the ranker.

Keeping the synonym tables in one place means "ecru" scores as "cream" both
when we read the shopper's sentence and when we read a retailer's product
title.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

# --------------------------------------------------------------------------
# Colours
# --------------------------------------------------------------------------
COLOUR_SYNONYMS: Dict[str, Set[str]] = {
    "black": {"black", "jet", "onyx", "pitch"},
    "white": {"white", "optic white", "bright white"},
    "cream": {
        "cream",
        "ecru",
        "off-white",
        "off white",
        "ivory",
        "bone",
        "chalk",
        "oat",
        "oatmeal",
    },
    "navy": {"navy", "midnight", "dark blue", "ink"},
    "blue": {"blue", "cobalt", "sky", "denim blue", "indigo", "azure"},
    "charcoal": {"charcoal", "graphite", "anthracite", "slate"},
    "grey": {"grey", "gray", "silver", "marle", "heather grey", "heather gray", "ash"},
    "brown": {"brown", "chocolate", "espresso", "walnut", "coffee", "mocha"},
    "tan": {"tan", "camel", "caramel", "biscuit", "toffee", "cognac"},
    "beige": {"beige", "sand", "stone", "greige", "khaki beige", "taupe", "putty"},
    "olive": {"olive", "army green", "fatigue", "moss"},
    "green": {"green", "forest", "emerald", "sage", "bottle green"},
    "burgundy": {"burgundy", "wine", "maroon", "oxblood", "claret"},
    "rust": {"rust", "terracotta", "brick", "clay"},
    "pink": {"pink", "rose", "blush", "dusty pink"},
    "red": {"red", "scarlet", "crimson"},
    "yellow": {"yellow", "mustard", "ochre", "butter"},
    "purple": {"purple", "plum", "aubergine", "violet"},
    "khaki": {"khaki", "drab"},
    "ecru": set(),  # handled as an alias of cream above
}
COLOUR_SYNONYMS.pop("ecru")

# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------
MATERIAL_SYNONYMS: Dict[str, Set[str]] = {
    "linen": {"linen", "flax", "linen-blend", "linen blend"},
    "cotton": {"cotton", "organic cotton", "poplin", "oxford cotton", "twill cotton"},
    "wool": {"wool", "woollen", "woolen", "tweed", "flannel wool"},
    "merino": {"merino", "merino wool"},
    "cashmere": {"cashmere"},
    "silk": {"silk", "sandwashed silk"},
    "denim": {"denim", "selvedge", "selvage"},
    "leather": {"leather", "nappa", "calfskin"},
    "suede": {"suede", "nubuck"},
    "corduroy": {"corduroy", "cord", "needlecord"},
    "nylon": {"nylon", "ripstop"},
    "polyester": {"polyester", "recycled polyester"},
    "tencel": {"tencel", "lyocell", "modal"},
    "seersucker": {"seersucker"},
    "jersey": {"jersey", "loopback", "french terry"},
    "hemp": {"hemp"},
}

# --------------------------------------------------------------------------
# Fits
# --------------------------------------------------------------------------
FIT_SYNONYMS: Dict[str, Set[str]] = {
    "relaxed": {"relaxed", "easy", "loose", "loose-fit", "casual fit"},
    "oversized": {"oversized", "oversize", "boxy", "baggy", "roomy"},
    "slim": {"slim", "slim-fit", "narrow", "fitted"},
    "skinny": {"skinny", "super slim"},
    "regular": {"regular", "classic fit", "standard fit"},
    "straight": {"straight", "straight-leg", "straight leg"},
    "wide-leg": {"wide-leg", "wide leg", "wideleg", "wide-fit"},
    "tapered": {"tapered", "carrot"},
    "cropped": {"cropped", "crop"},
    "tailored": {"tailored", "structured"},
}

# --------------------------------------------------------------------------
# Categories. The alias list doubles as the matcher against product titles.
# --------------------------------------------------------------------------
CATEGORY_SYNONYMS: Dict[str, Set[str]] = {
    "shirt": {
        "shirt",
        "shirts",
        "button-up",
        "button up",
        "button-down",
        "oxford shirt",
        "camp collar",
    },
    "overshirt": {"overshirt", "shacket", "shirt jacket", "chore shirt"},
    "t-shirt": {"t-shirt", "tshirt", "t shirt", "tee", "tees", "t-shirts"},
    "polo": {"polo", "polos", "polo shirt"},
    "knitwear": {"knit", "knitwear", "jumper", "sweater", "cardigan", "pullover", "crewneck knit"},
    "hoodie": {
        "hoodie",
        "hoodies",
        "hood",
        "hooded sweatshirt",
        "sweatshirt",
        "crewneck sweat",
        "crew sweat",
        "sweat",
        "sweats",
    },
    "trousers": {"trousers", "pants", "pant", "slacks", "trouser"},
    "trackpants": {
        "trackpants",
        "trackpant",
        "track pant",
        "track pants",
        "sweatpants",
        "sweatpant",
        "sweat pant",
        "sweat pants",
        "joggers",
        "jogger",
        "jogger pant",
        "trackies",
    },
    "chinos": {"chino", "chinos"},
    "jeans": {"jeans", "jean", "denim pants", "denim jeans", "denim pant", "jean pant"},
    "shorts": {"shorts", "short"},
    "jacket": {
        "jacket",
        "bomber",
        "harrington",
        "chore jacket",
        "windbreaker",
        "track top",
        "track jacket",
        "anorak",
        "gilet",
    },
    "blazer": {"blazer", "sport coat", "sports jacket", "suit jacket"},
    "coat": {"coat", "overcoat", "trench", "parka", "puffer"},
    "suit": {"suit", "two-piece", "three-piece"},
    "singlet": {"singlet", "singlets", "tank", "tank top", "muscle tank", "muscle tee", "vest top"},
    "shoes": {
        "shoes",
        "shoe",
        "sneakers",
        "sneaker",
        "trainers",
        "loafers",
        "boots",
        "boot",
        "derbies",
        "oxfords",
        "sandals",
        "slides",
        "clogs",
    },
    "accessories": {
        "belt",
        "cap",
        "hat",
        "bucket hat",
        "beanie",
        "scarf",
        "socks",
        "sock",
        "tie",
        "sunglasses",
        "bag",
        "tote",
        "backpack",
        "wallet",
        "card holder",
        "cardholder",
        "cc holder",
        "necklace",
        "bracelet",
        "keyring",
        "water bottle",
        "bottle",
        "watch",
    },
    "underwear": {"underwear", "boxer", "boxers", "boxer brief", "briefs", "trunk", "trunks"},
    "swimwear": {
        "swim shorts",
        "swim short",
        "swimwear",
        "board shorts",
        "board short",
        "boardshorts",
        "boardshort",
        "swim trunks",
        "swim trunk",
        "boardie",
        "boardies",
    },
}

# Broader shopper terms also include their narrower garment categories.
CATEGORY_CHILDREN: Dict[str, Set[str]] = {
    "trousers": {"chinos", "trackpants"},
    "jacket": {"blazer"},
}

# --------------------------------------------------------------------------
# Styles and occasions
# --------------------------------------------------------------------------
STYLE_TERMS: Dict[str, Set[str]] = {
    "smart casual": {"smart casual", "smart-casual"},
    "minimal": {"minimal", "minimalist", "clean", "understated", "pared back", "pared-back"},
    "streetwear": {"streetwear", "street style"},
    "workwear": {"workwear", "utility", "military"},
    "tailoring": {"tailoring", "formal", "black tie", "business"},
    "vintage": {"vintage", "retro", "heritage"},
    "preppy": {"preppy", "ivy", "collegiate"},
    "technical": {"technical", "performance", "gorpcore", "outdoor"},
    "resort": {"resort", "holiday", "vacation", "beachy"},
    "japanese": {"japanese", "japan-made"},
}

OCCASION_TERMS: Dict[str, Set[str]] = {
    "wedding": {"wedding", "groomsman", "groom"},
    "work": {"work", "office", "interview", "business meeting"},
    "holiday": {"holiday", "vacation", "resort", "travel", "trip"},
    "party": {"party", "night out", "club", "birthday"},
    "date": {"date night", "date"},
    "everyday": {"everyday", "daily", "weekend", "casual wear"},
    "formal event": {"formal event", "gala", "black tie"},
    "beach": {"beach", "pool", "seaside"},
    "festival": {"festival"},
}

SEASON_TERMS: Dict[str, Set[str]] = {
    "summer": {"summer", "hot weather", "warm weather"},
    "winter": {"winter", "cold weather"},
    "autumn": {"autumn", "fall", "transitional"},
    "spring": {"spring"},
}

# --------------------------------------------------------------------------
# Brand style hints. Used for "something like <brand>" queries so we can turn a
# brand reference into style signals instead of an unsatisfiable brand filter.
# --------------------------------------------------------------------------
BRAND_STYLE_HINTS: Dict[str, List[str]] = {
    "cos": ["minimal", "relaxed", "clean"],
    "arket": ["minimal", "everyday"],
    "uniqlo": ["minimal", "everyday"],
    "zara": ["smart casual", "trend"],
    "aime leon dore": ["preppy", "vintage"],
    "our legacy": ["minimal", "relaxed"],
    "acne studios": ["minimal", "oversized"],
    "carhartt": ["workwear", "relaxed"],
    "patagonia": ["technical", "outdoor"],
    "rrl": ["vintage", "workwear"],
    "sunspel": ["minimal", "everyday"],
    "massimo dutti": ["smart casual", "tailoring"],
}

SIZE_ALIASES: Dict[str, str] = {
    "extra small": "xs",
    "x-small": "xs",
    "xs": "xs",
    "small": "s",
    "s": "s",
    "medium": "m",
    "med": "m",
    "m": "m",
    "large": "l",
    "l": "l",
    "extra large": "xl",
    "x-large": "xl",
    "xl": "xl",
    "xxl": "xxl",
    "2xl": "xxl",
    "xxxl": "xxxl",
    "3xl": "xxxl",
}

STOPWORDS: Set[str] = {
    "a",
    "an",
    "and",
    "the",
    "for",
    "with",
    "that",
    "this",
    "some",
    "any",
    "me",
    "i",
    "my",
    "of",
    "to",
    "in",
    "on",
    "at",
    "is",
    "are",
    "be",
    "im",
    "want",
    "need",
    "looking",
    "look",
    "find",
    "show",
    "get",
    "buy",
    "shop",
    "please",
    "something",
    "anything",
    "like",
    "similar",
    "under",
    "below",
    "over",
    "less",
    "than",
    "more",
    "about",
    "around",
    "up",
    "it",
    "its",
    "would",
    "can",
    "you",
    "your",
    "us",
    "we",
    "or",
    "but",
    "very",
    "really",
    "just",
    "good",
    "nice",
    "great",
    "best",
    "new",
    "from",
    "by",
    "out",
    "all",
    "size",
    "sized",
    "ships",
    "ship",
    "shipping",
    "deliver",
    "delivery",
    "not",
    "no",
    "except",
    "excluding",
    "avoid",
    "without",
    "other",
    "apart",
    "sale",
    "discount",
    "discounted",
    "deal",
    "deals",
    "clearance",
    "reduced",
    "price",
    "cheap",
    "cheaper",
    "cheapest",
    "budget",
    "max",
    "maximum",
    "minimum",
    "min",
    "dollars",
    "dollar",
    "aud",
    "usd",
    "outfit",
    "men",
    "mens",
    "man",
    "male",
    "wear",
    "wearing",
    # Instruction-shaped words are never garment attributes; excluding them
    # stops an injection attempt from turning into search keywords.
    "ignore",
    "previous",
    "prior",
    "instruction",
    "instructions",
    "prompt",
    "system",
    "assistant",
    "reveal",
    "disregard",
    "override",
    "forget",
}

CURRENCY_SYMBOLS: Dict[str, str] = {"$": "AUD", "£": "GBP", "€": "EUR", "¥": "JPY"}
CURRENCY_CODES: Set[str] = {"aud", "usd", "gbp", "eur", "nzd", "cad", "jpy", "sgd"}

# City -> (country code, postcode hint). Used to resolve "ships to Sydney".
CITY_COUNTRY: Dict[str, str] = {
    "sydney": "AU",
    "melbourne": "AU",
    "brisbane": "AU",
    "perth": "AU",
    "adelaide": "AU",
    "canberra": "AU",
    "hobart": "AU",
    "darwin": "AU",
    "auckland": "NZ",
    "wellington": "NZ",
    "london": "GB",
    "manchester": "GB",
    "edinburgh": "GB",
    "new york": "US",
    "nyc": "US",
    "los angeles": "US",
    "chicago": "US",
    "toronto": "CA",
    "vancouver": "CA",
    "singapore": "SG",
    "tokyo": "JP",
    "berlin": "DE",
    "paris": "FR",
}
COUNTRY_NAMES: Dict[str, str] = {
    "australia": "AU",
    "new zealand": "NZ",
    "united kingdom": "GB",
    "uk": "GB",
    "england": "GB",
    "united states": "US",
    "usa": "US",
    "america": "US",
    "canada": "CA",
    "singapore": "SG",
    "japan": "JP",
    "germany": "DE",
    "france": "FR",
}

_WORD_BOUNDARY_CACHE: Dict[str, re.Pattern[str]] = {}


def _pattern_for(term: str) -> re.Pattern[str]:
    cached = _WORD_BOUNDARY_CACHE.get(term)
    if cached is None:
        cached = re.compile(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])", re.IGNORECASE)
        _WORD_BOUNDARY_CACHE[term] = cached
    return cached


def find_terms(text: str, table: Dict[str, Set[str]]) -> List[str]:
    """Return canonical terms from ``table`` that appear in ``text``.

    Longer aliases are tested first so "wide leg" wins over "leg".
    """
    if not text:
        return []
    found: List[str] = []
    for canonical, aliases in table.items():
        candidates = sorted({canonical, *aliases}, key=len, reverse=True)
        for alias in candidates:
            if _pattern_for(alias).search(text):
                if canonical not in found:
                    found.append(canonical)
                break
    return found


def _alias_matches(text: str, table: Dict[str, Set[str]]) -> List[Tuple[int, int, str]]:
    matches = []
    for canonical, aliases in table.items():
        for alias in {canonical, *aliases}:
            for match in _pattern_for(alias).finditer(text):
                matches.append((match.start(), match.end(), canonical))
    # A match inside a longer one ("shorts" in "swim shorts") is not separate.
    return [
        m
        for m in matches
        if not any(o[0] <= m[0] and m[1] <= o[1] and (o[1] - o[0]) > (m[1] - m[0]) for o in matches)
    ]


def find_categories(text: str) -> List[str]:
    """Categories named in ``text``, ignoring words inside a longer garment name."""
    found: List[str] = []
    for _, _, canonical in sorted(_alias_matches(text or "", CATEGORY_SYNONYMS)):
        if canonical not in found:
            found.append(canonical)
    return found


def classify_category(text: str) -> Optional[str]:
    """The garment a product title describes.

    English titles end with the head noun ("Linen Shirt Jacket" is a jacket,
    "Short Sleeve Shirt" is a shirt), so the last-ending, longest match wins.
    """
    matches = _alias_matches(text or "", CATEGORY_SYNONYMS)
    if not matches:
        return None
    return max(matches, key=lambda m: (m[1], m[1] - m[0]))[2]


def expand_categories(categories: Sequence[str]) -> List[str]:
    expanded = list(categories)
    for category in categories:
        for child in sorted(CATEGORY_CHILDREN.get(category, ())):
            if child not in expanded:
                expanded.append(child)
    return expanded


def canonicalise(term: str, table: Dict[str, Set[str]]) -> Optional[str]:
    """Map a single free-text term onto its canonical form."""
    if not term:
        return None
    lowered = term.strip().lower()
    for canonical, aliases in table.items():
        if lowered == canonical or lowered in aliases:
            return canonical
    for canonical, aliases in table.items():
        for alias in {canonical, *aliases}:
            if _pattern_for(alias).search(lowered):
                return canonical
    return None


def canonicalise_all(terms: Sequence[str], table: Dict[str, Set[str]]) -> List[str]:
    out: List[str] = []
    for term in terms:
        canonical = canonicalise(term, table)
        value = canonical or term.strip().lower()
        if value and value not in out:
            out.append(value)
    return out


def normalise_size(value: str) -> str:
    """Map "size medium"/"Med" to a comparable token; numeric sizes pass through."""
    if not value:
        return ""
    text = re.sub(r"\b(size|sized)\b", " ", value.lower()).strip()
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text in SIZE_ALIASES:
        return SIZE_ALIASES[text]
    match = re.fullmatch(r"(\d{2,3})(?:\s*(?:inch|in|\"|w|waist))?", text)
    if match:
        return match.group(1)
    return text


def tokenise(text: str) -> List[str]:
    return [token for token in re.split(r"[^\w'-]+", (text or "").lower()) if token]


def content_tokens(text: str) -> List[str]:
    """Tokens without stopwords or short words; model numbers like "501" are kept."""
    return [token for token in tokenise(text) if token not in STOPWORDS and len(token) > 2]
