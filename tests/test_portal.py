from core import portal
from core.runner_portal import PortalOps


def test_modifier_ocr_matching_handles_supplied_tooltip_text():
    assert portal.modifiers_from_text(
        "Sky Ruins Portal Tier 5 portal 1.96x 1.3x Resistance 1.63x Short Range"
    ) == ["Resistance", "Short Range"]
    assert portal.modifiers_from_text(
        "Sky Ruins Portal Tier 5 1.68x 1.26x Short Range 2.12x Shielded"
    ) == ["Shielded", "Short Range"]


def test_modifier_ocr_matching_covers_every_game_modifier():
    text = "Came Modifier Resistance Speedy Shielded Traitless Short Range Upgrade Cap"
    assert portal.modifiers_from_text(text) == list(portal.PORTAL_MODIFIERS)


def test_tier_reader_handles_observed_portal_selection_ocr_error():
    assert portal.tier_from_text("Tier 5") == "5"
    assert portal.tier_from_text("�rier5") == "5"


def test_owned_choice_never_activates_an_avoided_modifier():
    options = [
        {"tier": "5", "modifiers": ["Shielded", "Short Range"]},
        {"tier": "1", "modifiers": ["Resistance", "Short Range"]},
        {"tier": "5", "modifiers": ["Speedy"]},
    ]
    choice = portal.choose_portal(
        options, preferred=["Speedy", "Resistance"], avoided=["Short Range"])
    assert choice is options[2]


def test_owned_choice_rejects_unknown_modifiers_when_filters_are_active():
    options = [{"tier": "5", "modifiers": [], "modifiers_readable": False}]
    assert portal.choose_portal(options, avoided=["Traitless"]) is None


def test_forced_reward_choice_uses_least_bad_card_when_all_are_avoided():
    options = [
        {"tier": "5", "modifiers": ["Short Range", "Traitless"]},
        {"tier": "5", "modifiers": ["Short Range"]},
        {"tier": "5", "modifiers": ["Short Range", "Shielded"]},
    ]
    assert portal.choose_portal(
        options, preferred=["Shielded"], avoided=["Short Range"], require_safe=False
    ) is options[2]


def test_inventory_cards_match_name_and_tier_from_ocr_lines():
    lines = [
        {"text": "�rier5", "cx": 270, "cy": 105},
        {"text": "Sky Ruins Portal", "cx": 280, "cy": 210},
        {"text": "Tier 1", "cx": 430, "cy": 105},
        {"text": "Sky Ruins Portal", "cx": 430, "cy": 210},
        {"text": "Tier 5", "cx": 580, "cy": 105},
        {"text": "Summer, Portal", "cx": 580, "cy": 210},
        # Repeated selected title in the right-side detail pane: excluded.
        {"text": "Sky Ruins Portal", "cx": 850, "cy": 150},
    ]
    task = {"map": "Sky Ruins Portal", "portal_tier": "5"}
    cards = PortalOps()._portal_inventory_candidates(lines, task)
    assert [(card["name"], card["tier"]) for card in cards] == [
        ("Sky Ruins Portal", "5")]


def test_any_portal_any_tier_includes_every_visible_card():
    lines = [
        {"text": "Tier 5", "cx": 270, "cy": 105},
        {"text": "Sky Ruins Portal", "cx": 280, "cy": 210},
        {"text": "Tier 1", "cx": 430, "cy": 105},
        {"text": "Summer Portal", "cx": 430, "cy": 210},
    ]
    cards = PortalOps()._portal_inventory_candidates(
        lines, {"map": "Any Portal", "portal_tier": "Any"})
    assert [(card["name"], card["tier"]) for card in cards] == [
        ("Sky Ruins Portal", "5"), ("Summer Portal", "1")]
