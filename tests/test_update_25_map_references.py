import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REFERENCES = (
    "Assets/map/Story/Crimson Shore.png",
    "Assets/map/Raid/Snowy Castle Act1.png",
    "Assets/map/Raid/Snowy Castle Act2.png",
    "Assets/map/Raid/Snowy Castle Act3.png",
)


def test_absolute_dream_map_references_are_normalized() -> None:
    for relative_path in EXPECTED_REFERENCES:
        image_path = ROOT / relative_path
        data = image_path.read_bytes()

        assert data.startswith(b"\x89PNG\r\n\x1a\n"), relative_path
        width, height = struct.unpack(">II", data[16:24])
        assert (width, height) == (1152, 756), relative_path
