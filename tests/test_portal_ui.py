from pathlib import Path


APP_JS = (Path(__file__).resolve().parents[1] / "ui" / "app.js").read_text(encoding="utf-8")


def test_task_builder_exposes_portal_mode_and_all_tiers():
    assert "label: 'Portal'" in APP_JS
    assert "maps: ['Any Portal', 'Sky Ruins Portal', 'Summer Portal']" in APP_JS
    assert "tiers: ['Any', '1', '2', '3', '4', '5']" in APP_JS


def test_task_builder_exposes_every_modifier_as_preferred_or_avoided():
    assert "const PORTAL_MODIFIERS = ['Resistance', 'Shielded', 'Short Range', 'Speedy', 'Traitless', 'Upgrade Cap']" in APP_JS
    assert "Preferred Modifiers" in APP_JS
    assert "Avoid Modifiers" in APP_JS
    assert "portal_preferred_modifiers" in APP_JS
    assert "portal_avoided_modifiers" in APP_JS


def test_portal_tasks_do_not_offer_irrelevant_matchmaking_toggle():
    assert "t.mode !== 'tower' && t.mode !== 'portal'" in APP_JS
