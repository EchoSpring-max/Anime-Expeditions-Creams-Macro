"""Build the standalone Windows Map Camera executable."""
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
ENTRY = os.path.join(ROOT, "tools", "map_camera.py")


def main() -> None:
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "Anime-Expeditions-Map-Camera",
        "--icon", os.path.join(ROOT, "logo.ico"),
        "--paths", ROOT,
        ENTRY,
    ]
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
