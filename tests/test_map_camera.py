from datetime import datetime
from pathlib import Path

import numpy as np

from tools import map_camera


def test_safe_component_removes_windows_path_characters():
    assert map_camera.safe_component('  Crimson: Shore?/Act 1  ') == "Crimson ShoreAct 1"
    assert map_camera.safe_component("...") == "Unnamed Map"


def test_next_capture_path_is_grouped_and_never_overwrites(tmp_path: Path):
    moment = datetime(2026, 9, 8, 14, 30, 5)
    first = map_camera.next_capture_path(tmp_path, "Story", "Crimson Shore", moment)
    assert first == tmp_path / "Story" / "Crimson Shore" / "Crimson Shore_2026-09-08_14-30-05.png"
    first.parent.mkdir(parents=True)
    first.touch()
    second = map_camera.next_capture_path(tmp_path, "Story", "Crimson Shore", moment)
    assert second.name == "Crimson Shore_2026-09-08_14-30-05_2.png"


def test_save_png_round_trips_unicode_path(tmp_path: Path):
    frame = map_camera.cv2.imread(str(
        map_camera.REPO_DIR / "Assets" / "maps" / "Crimson Shore" / "Crimson Shore.png"))
    target = tmp_path / "Mäp" / "capture.png"
    map_camera.save_png(frame, target)
    loaded = map_camera.cv2.imdecode(
        np.frombuffer(target.read_bytes(), np.uint8), map_camera.cv2.IMREAD_COLOR)
    assert target.is_file()
    assert loaded is not None


def test_find_assets_dir_accepts_macro_or_assets_folder(tmp_path: Path):
    assets = tmp_path / "Assets"
    assets.mkdir()
    assert map_camera.find_assets_dir(tmp_path) == assets
    assert map_camera.find_assets_dir(assets) == assets
    assert map_camera.find_assets_dir(tmp_path / "missing") is None


def test_panorama_capture_path_numbers_views(tmp_path: Path):
    path = map_camera.panorama_capture_path(
        tmp_path, "Raid", "Snowy Castle", "2026-09-08_15-00", 3)
    assert path == (tmp_path / "Raid" / "Snowy Castle" / "Panorama_2026-09-08_15-00" /
                    "Snowy Castle_view_03.png")


def test_pan_camera_right_drags_left_and_always_releases(monkeypatch):
    events = []

    class FakeMouse:
        def move_to(self, x, y):
            events.append(("move", x, y))

        def down(self, button):
            events.append(("down", button))

        def up(self, button):
            events.append(("up", button))

    monkeypatch.setattr(map_camera.vision, "ref_to_screen", lambda _hwnd, x, y: (x, y))
    monkeypatch.setattr(map_camera.time, "sleep", lambda _seconds: None)
    map_camera.pan_camera(FakeMouse(), 123, 120, "Right", duration=0, steps=2)
    assert events[0] == ("move", 576, 378)
    assert events[1] == ("down", "right")
    assert events[-2] == ("move", 456, 378)
    assert events[-1] == ("up", "right")
