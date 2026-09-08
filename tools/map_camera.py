"""Small Roblox map screenshot utility for Cream's Macro.

Run from source with ``python tools/map_camera.py`` or build the standalone
Windows executable with ``python build_map_camera.py``. Captures are normalized
to the macro's 1152x756 reference viewport before being saved.
"""
from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Running this file directly puts tools/ rather than the repository root on
# sys.path. Add the root so the same core modules are used in source and frozen
# builds.
REPO_DIR = Path(__file__).resolve().parent.parent
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from core import config  # noqa: E402
from core import constants  # noqa: E402
from core import vision  # noqa: E402
from core import window as wm  # noqa: E402
from core.mouse import Mouse  # noqa: E402


CATEGORIES = ("Story", "Raid", "Expedition", "Event")
CAPTURE_DIR = Path(constants.APP_DIR) / "MapCaptures"


def safe_component(value: str, fallback: str = "Unnamed Map") -> str:
    """Return a Windows-safe folder/file component."""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(value or "")).strip().strip(".")
    value = re.sub(r"\s+", " ", value)
    return value or fallback


def next_capture_path(root: Path, category: str, map_name: str,
                      captured_at: datetime | None = None) -> Path:
    """Choose a timestamped path without overwriting an earlier capture."""
    category = safe_component(category, "Other")
    map_name = safe_component(map_name)
    stamp = (captured_at or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    folder = Path(root) / category / map_name
    candidate = folder / f"{map_name}_{stamp}.png"
    suffix = 2
    while candidate.exists():
        candidate = folder / f"{map_name}_{stamp}_{suffix}.png"
        suffix += 1
    return candidate


def panorama_capture_path(root: Path, category: str, map_name: str,
                          session: str, index: int) -> Path:
    """Path for one numbered view in an automatic pan sequence."""
    category = safe_component(category, "Other")
    map_name = safe_component(map_name)
    folder = Path(root) / category / map_name / f"Panorama_{safe_component(session, 'capture')}"
    return folder / f"{map_name}_view_{max(1, int(index)):02d}.png"


def save_png(frame, path: Path) -> None:
    """Save BGR pixels to any Unicode path and raise on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", frame)
    if not ok:
        raise RuntimeError("OpenCV could not encode the screenshot")
    path.write_bytes(encoded.tobytes())


def find_assets_dir(selection: Path) -> Path | None:
    """Accept either the macro folder or its Assets folder."""
    selection = Path(selection)
    if selection.is_dir() and selection.name.casefold() == "assets":
        return selection
    assets = selection / "Assets"
    return assets if assets.is_dir() else None


def capture_roblox_frame(hwnd: int | None = None):
    """Capture the Roblox client and normalize it to macro coordinates."""
    hwnd = hwnd or wm.find_roblox_window()
    if not hwnd:
        raise RuntimeError("Roblox was not found. Start the game and try again.")

    # PrintWindow reads Roblox itself, not whatever overlaps it, so the camera
    # can remain visible. Some GPU configurations return no backing-store frame;
    # in that case bring Roblox above the tool and use the macro's live capture.
    frame = vision.capture_window_region_bgr(hwnd)
    if frame is None or frame.size == 0:
        wm.bring_to_top(hwnd)
        time.sleep(0.35)
        frame = vision.capture_game_bgr(hwnd)
    if frame is None or frame.size == 0:
        raise RuntimeError("Roblox returned a blank frame. Keep the game visible and retry.")
    if frame.shape[:2] != (config.FIXED_WIN_H, config.FIXED_WIN_W):
        frame = cv2.resize(
            frame, (config.FIXED_WIN_W, config.FIXED_WIN_H), interpolation=cv2.INTER_AREA)
    return frame


def pan_camera(mouse: Mouse, hwnd: int, pixels: int, direction: str,
               duration: float = 0.3, steps: int = 18) -> None:
    """Right-drag inside Roblox once, always releasing the mouse button."""
    pixels = max(1, abs(int(pixels)))
    # Dragging the scene left turns the camera view right (and vice versa).
    delta = -pixels if str(direction).casefold() == "right" else pixels
    start = vision.ref_to_screen(hwnd, config.FIXED_WIN_W // 2, config.FIXED_WIN_H // 2)
    end = vision.ref_to_screen(
        hwnd, config.FIXED_WIN_W // 2 + delta, config.FIXED_WIN_H // 2)
    mouse.move_to(*start)
    time.sleep(0.04)
    mouse.down("right")
    try:
        step_delay = max(0.0, float(duration)) / max(1, int(steps))
        for step in range(1, max(1, int(steps)) + 1):
            x = start[0] + (end[0] - start[0]) * step / max(1, int(steps))
            y = start[1] + (end[1] - start[1]) * step / max(1, int(steps))
            mouse.move_to(round(x), round(y))
            time.sleep(step_delay)
    finally:
        mouse.up("right")


class MapCamera:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.frame = None
        self.last_path: Path | None = None
        self.preview_image = None
        self.hotkey_registered = False
        self.assets_dir = find_assets_dir(Path(constants.APP_DIR))
        self.auto_running = False
        self.auto_stop_requested = False
        self.auto_hwnd = 0
        self.auto_index = 0
        self.auto_total = 0
        self.auto_session = ""
        self.auto_mouse = Mouse()

        root.title("Anime Expeditions Map Camera")
        root.geometry("680x650")
        root.minsize(600, 560)
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", self.close)

        shell = ttk.Frame(root, padding=14)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Map Camera", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            shell,
            text="Position the Roblox camera, enter a name, then press F8 or Capture.",
        ).pack(anchor="w", pady=(2, 12))

        form = ttk.Frame(shell)
        form.pack(fill="x")
        ttk.Label(form, text="Category").grid(row=0, column=0, sticky="w")
        ttk.Label(form, text="Map name").grid(row=0, column=1, sticky="w", padx=(10, 0))
        ttk.Label(form, text="Delay").grid(row=0, column=2, sticky="w", padx=(10, 0))

        self.category = tk.StringVar(value="Story")
        self.map_name = tk.StringVar(value="New Map")
        self.delay = tk.StringVar(value="0")
        ttk.Combobox(form, textvariable=self.category, values=CATEGORIES,
                     state="readonly", width=13).grid(row=1, column=0, sticky="ew")
        ttk.Entry(form, textvariable=self.map_name).grid(row=1, column=1, sticky="ew", padx=(10, 0))
        ttk.Combobox(form, textvariable=self.delay, values=("0", "2", "5"),
                     state="readonly", width=7).grid(row=1, column=2, sticky="ew", padx=(10, 0))
        form.columnconfigure(1, weight=1)

        pan_form = ttk.LabelFrame(shell, text="Automatic panorama", padding=8)
        pan_form.pack(fill="x", pady=(12, 0))
        for column, label in enumerate(("Views", "Step (pixels)", "Direction", "Settle (seconds)")):
            ttk.Label(pan_form, text=label).grid(row=0, column=column, sticky="w", padx=(0, 8))
        self.pan_views = tk.StringVar(value="8")
        self.pan_step = tk.StringVar(value="140")
        self.pan_direction = tk.StringVar(value="Right")
        self.pan_settle = tk.StringVar(value="0.7")
        ttk.Spinbox(pan_form, from_=2, to=36, textvariable=self.pan_views, width=8).grid(
            row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Spinbox(pan_form, from_=20, to=500, increment=10,
                    textvariable=self.pan_step, width=12).grid(
            row=1, column=1, sticky="ew", padx=(0, 8))
        ttk.Combobox(pan_form, textvariable=self.pan_direction, values=("Right", "Left"),
                     state="readonly", width=10).grid(row=1, column=2, sticky="ew", padx=(0, 8))
        ttk.Spinbox(pan_form, from_=0.1, to=5.0, increment=0.1,
                    textvariable=self.pan_settle, width=12).grid(row=1, column=3, sticky="ew")
        ttk.Label(
            pan_form,
            text="Captures the starting view, then right-drags and captures each next angle. F9 stops safely.",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))

        actions = ttk.Frame(shell)
        actions.pack(fill="x", pady=12)
        self.capture_button = ttk.Button(actions, text="Capture (F8)", command=self.begin_capture)
        self.capture_button.pack(side="left")
        self.auto_button = ttk.Button(actions, text="Auto Pan + Capture", command=self.begin_auto_pan)
        self.auto_button.pack(side="left", padx=(8, 0))
        self.stop_button = ttk.Button(
            actions, text="Stop (F9)", command=self.stop_auto_pan, state="disabled")
        self.stop_button.pack(side="left", padx=(8, 0))
        self.install_button = ttk.Button(
            actions, text="Install in Macro", command=self.install_capture, state="disabled")
        self.install_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open Captures", command=self.open_captures).pack(side="left")

        self.preview = ttk.Label(shell, text="No capture yet", anchor="center", relief="sunken")
        self.preview.pack(fill="both", expand=True)
        self.status = tk.StringVar(value=f"Saves {config.FIXED_WIN_W}×{config.FIXED_WIN_H} PNG files")
        ttk.Label(shell, textvariable=self.status).pack(anchor="w", pady=(10, 0))

        self._register_hotkey()

    def _register_hotkey(self) -> None:
        try:
            import keyboard
            keyboard.add_hotkey("f8", lambda: self.root.after(0, self.begin_capture))
            keyboard.add_hotkey("f9", lambda: self.root.after(0, self.stop_auto_pan))
            self.hotkey_registered = True
        except Exception:
            # The button remains available when Windows denies global hooks.
            self.root.bind("<F8>", lambda _event: self.begin_capture())
            self.root.bind("<F9>", lambda _event: self.stop_auto_pan())

    def begin_capture(self) -> None:
        if str(self.capture_button["state"]) == "disabled":
            return
        try:
            delay = max(0, int(self.delay.get()))
        except ValueError:
            delay = 0
        self.capture_button.configure(state="disabled")
        self.status.set(f"Capturing in {delay} seconds…" if delay else "Capturing Roblox…")
        self.root.after(delay * 1000, self.take_capture)

    def take_capture(self) -> None:
        try:
            frame = capture_roblox_frame()
            path = next_capture_path(CAPTURE_DIR, self.category.get(), self.map_name.get())
            save_png(frame, path)
            self.frame = frame
            self.last_path = path
            self._show_preview(frame)
            self.install_button.configure(state="normal")
            self.status.set(f"Saved: {path}")
        except Exception as exc:
            self.status.set(str(exc))
            messagebox.showerror("Map Camera", str(exc), parent=self.root)
        finally:
            self.capture_button.configure(state="normal")
            self.root.lift()

    def begin_auto_pan(self) -> None:
        if self.auto_running or str(self.capture_button["state"]) == "disabled":
            return
        try:
            views = min(36, max(2, int(self.pan_views.get())))
            pixels = min(500, max(20, int(self.pan_step.get())))
            settle = min(5.0, max(0.1, float(self.pan_settle.get())))
        except ValueError:
            messagebox.showerror("Map Camera", "Views, step, and settle must be numbers.", parent=self.root)
            return
        hwnd = wm.find_roblox_window()
        if not hwnd:
            messagebox.showerror("Map Camera", "Roblox was not found. Start the game and try again.", parent=self.root)
            return

        self.auto_running = True
        self.auto_stop_requested = False
        self.auto_hwnd = hwnd
        self.auto_index = 0
        self.auto_total = views
        self.auto_pixels = pixels
        self.auto_settle_ms = round(settle * 1000)
        self.auto_session = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")[:-3]
        self.capture_button.configure(state="disabled")
        self.auto_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.install_button.configure(state="disabled")
        self.status.set(f"Starting automatic panorama: {views} views…")
        # A topmost tool window would receive the right-drag wherever it
        # overlaps Roblox. Keep the Tk event loop alive but hide its surface
        # until the panorama ends; global F9 still stops the sequence.
        self.root.withdraw()
        wm.activate_window(hwnd)
        try:
            delay = max(0, int(self.delay.get()))
        except ValueError:
            delay = 0
        self.root.after(delay * 1000 + 350, self._auto_pan_step)

    def _auto_pan_step(self) -> None:
        if self.auto_stop_requested:
            self._finish_auto_pan("Automatic panorama stopped.")
            return
        try:
            frame = capture_roblox_frame(self.auto_hwnd)
            self.auto_index += 1
            path = panorama_capture_path(
                CAPTURE_DIR, self.category.get(), self.map_name.get(),
                self.auto_session, self.auto_index)
            save_png(frame, path)
            self.frame = frame
            self.last_path = path
            self._show_preview(frame)
            self.status.set(f"Captured view {self.auto_index}/{self.auto_total}: {path.name}")
            if self.auto_index >= self.auto_total:
                self._finish_auto_pan(
                    f"Panorama complete: {self.auto_total} views saved in {path.parent}")
                return
            wm.activate_window(self.auto_hwnd)
            pan_camera(
                self.auto_mouse, self.auto_hwnd, self.auto_pixels,
                self.pan_direction.get())
            self.root.after(self.auto_settle_ms, self._auto_pan_step)
        except Exception as exc:
            self._finish_auto_pan(str(exc), error=True)

    def stop_auto_pan(self) -> None:
        if self.auto_running:
            self.auto_stop_requested = True
            self.status.set("Stopping after the current camera step…")

    def _finish_auto_pan(self, status: str, error: bool = False) -> None:
        self.auto_running = False
        self.auto_stop_requested = False
        self.capture_button.configure(state="normal")
        self.auto_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        if self.frame is not None:
            self.install_button.configure(state="normal")
        self.status.set(status)
        self.root.deiconify()
        self.root.lift()
        if error:
            messagebox.showerror("Map Camera", status, parent=self.root)

    def _show_preview(self, frame) -> None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        image.thumbnail((570, 375), Image.Resampling.LANCZOS)
        self.preview_image = ImageTk.PhotoImage(image)
        self.preview.configure(image=self.preview_image, text="")

    def install_capture(self) -> None:
        if self.frame is None:
            return
        if self.assets_dir is None:
            selected = filedialog.askdirectory(
                title="Select the macro folder (or its Assets folder)", parent=self.root)
            if not selected:
                return
            self.assets_dir = find_assets_dir(Path(selected))
            if self.assets_dir is None:
                messagebox.showerror(
                    "Map Camera", "That folder does not contain the macro's Assets folder.",
                    parent=self.root)
                return
        category = safe_component(self.category.get(), "Story")
        map_name = safe_component(self.map_name.get())
        target = self.assets_dir / "map" / category / f"{map_name}.png"
        if target.exists() and not messagebox.askyesno(
                "Replace map image?", f"Replace the existing image?\n\n{target}", parent=self.root):
            return
        try:
            save_png(self.frame, target)
            self.status.set(f"Installed: {target}")
            messagebox.showinfo("Map Camera", "Map image installed in the macro.", parent=self.root)
        except Exception as exc:
            messagebox.showerror("Map Camera", str(exc), parent=self.root)

    def open_captures(self) -> None:
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(CAPTURE_DIR)  # type: ignore[attr-defined]

    def close(self) -> None:
        if self.hotkey_registered:
            try:
                import keyboard
                keyboard.remove_hotkey("f8")
                keyboard.remove_hotkey("f9")
            except Exception:
                pass
        self.root.destroy()


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Map Camera currently supports Windows only.")
    wm.set_dpi_aware()
    root = tk.Tk()
    MapCamera(root)
    root.mainloop()


if __name__ == "__main__":
    main()
