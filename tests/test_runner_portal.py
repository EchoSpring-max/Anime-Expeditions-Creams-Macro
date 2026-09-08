import threading
from unittest.mock import Mock

from core.runner import MacroRunner


def _runner():
    return MacroRunner(Mock(), Mock(), Mock())


def test_portal_task_setup_uses_inventory_activation(monkeypatch):
    runner = _runner()
    expected_task = {"mode": "portal", "map": "Sky Ruins Portal", "portal_tier": "5"}
    called = []
    monkeypatch.setattr(
        runner, "_portal_activate_from_lobby",
        lambda hwnd, stop, task, webhook: called.append((hwnd, task, webhook)) or True)

    assert runner._run_task_setup(
        123, threading.Event(), expected_task, "portal", "Sky Ruins Portal",
        {}, 3, 8, {"enabled": False}) is True
    assert called == [(123, expected_task, {"enabled": False})]


def test_portal_reward_picker_is_checked_before_victory_in_runner_source():
    import inspect

    source = inspect.getsource(MacroRunner._wait_for_match_result)
    assert source.index("_portal_pick_reward_if_visible") < source.index(
        'vision.find_image(hwnd, "victory")')


def test_portal_repeat_uses_select_portal_not_repeat_stage():
    import inspect

    source = inspect.getsource(MacroRunner._handle_match_result)
    assert source.index("_portal_select_from_victory") < source.index(
        'repeat_image = "repeat_stage"')
