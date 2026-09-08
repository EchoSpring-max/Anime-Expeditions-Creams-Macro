"""Portal names, modifier OCR matching, and deterministic choice ranking."""
from __future__ import annotations

import re
from difflib import SequenceMatcher


PORTAL_NAMES = ("Any Portal", "Sky Ruins Portal", "Summer Portal")
PORTAL_TIERS = ("Any", "1", "2", "3", "4", "5")
PORTAL_MODIFIERS = (
    "Resistance",
    "Shielded",
    "Short Range",
    "Speedy",
    "Traitless",
    "Upgrade Cap",
)


def normalize_modifier_list(values) -> list[str]:
    """Keep known modifiers once, in the order exposed by the UI."""
    wanted = {str(value).strip().lower() for value in (values or [])}
    return [name for name in PORTAL_MODIFIERS if name.lower() in wanted]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", str(text or "").lower())


def modifiers_from_text(text: str) -> list[str]:
    """Read the six known modifier labels from noisy whole-screen OCR."""
    words = _words(text)
    ngrams = set(words)
    ngrams.update(" ".join(words[i:i + 2]) for i in range(max(0, len(words) - 1)))
    found = []
    for modifier in PORTAL_MODIFIERS:
        target = modifier.lower()
        threshold = 0.72 if " " in target else 0.76
        if any(SequenceMatcher(None, candidate, target).ratio() >= threshold for candidate in ngrams):
            found.append(modifier)
    return found


def portal_name_from_text(text: str) -> str | None:
    normalized = " ".join(_words(text))
    for name in PORTAL_NAMES[1:]:
        target = name.lower()
        if target in normalized or SequenceMatcher(None, normalized, target).ratio() >= 0.72:
            return name
    return None


def tier_from_text(text: str) -> str | None:
    # Windows OCR read the first Portal Selection badge as "�rier5" in the
    # supplied screenshot, while the neighbouring badges were clean. Keep
    # that observed missing-leading-letter variant alongside common I/1
    # confusions instead of requiring a perfect "Tier" token.
    match = re.search(r"\b(?:tier|rier|tler|t1er)\s*([1-5])\b", str(text or ""), re.IGNORECASE)
    return match.group(1) if match else None


def choose_portal(options: list[dict], preferred=None, avoided=None,
                  require_safe: bool = True) -> dict | None:
    """Choose the safest option, then the one matching most preferences.

    Owned portals use ``require_safe=True`` and are never run when a known
    avoided modifier is present. Reward offers use ``False`` because the game
    forces one of the three cards to be accepted; in that case the least-bad
    card is selected when all three contain an avoided modifier.
    """
    preferred_set = set(normalize_modifier_list(preferred))
    avoided_set = set(normalize_modifier_list(avoided))
    ranked = []
    for index, option in enumerate(options or []):
        modifiers = set(normalize_modifier_list(option.get("modifiers")))
        readable = bool(option.get("modifiers_readable", modifiers or not (
            preferred_set or avoided_set)))
        avoided_count = len(modifiers & avoided_set)
        if require_safe and (avoided_count or not readable):
            continue
        preferred_count = len(modifiers & preferred_set)
        try:
            tier = int(option.get("tier") or 0)
        except (TypeError, ValueError):
            tier = 0
        # Stable final tiebreak: keep the leftmost/first inventory card.
        rank = (avoided_count == 0, preferred_count, -avoided_count, tier, -index)
        ranked.append((rank, option))
    return max(ranked, default=(None, None), key=lambda item: item[0])[1]
