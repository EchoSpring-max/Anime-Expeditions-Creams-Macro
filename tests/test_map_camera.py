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
