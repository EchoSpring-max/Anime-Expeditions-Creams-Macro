"""Portal task navigation and modifier-aware portal selection."""
from __future__ import annotations

import re
import time
from difflib import SequenceMatcher

from . import ocr_windows
from . import portal
from . import vision
from . import window as wm


PORTAL_MENU_TIMEOUT = 10.0
PORTAL_CARD_SETTLE = 0.45
PORTAL_ACTIVATE_TIMEOUT = 10.0
PORTAL_REWARD_SCAN_INTERVAL = 1.0
PORTAL_REWARD_CARD_CENTERS = ((287, 390), (638, 390), (988, 390))


class PortalOps:
    @staticmethod
    def _portal_line_score(text: str, wanted: str) -> float:
        clean = re.sub(r"[^a-z0-9]", "", str(text or "").lower())
        target = re.sub(r"[^a-z0-9]", "", wanted.lower())
        if target and target in clean:
            return 1.0
        return SequenceMatcher(None, clean, target).ratio()

    @classmethod
    def _portal_find_line(cls, lines: list, wanted: str, minimum: float = 0.70):
        scored = [(cls._portal_line_score(line.get("text", ""), wanted), line)
                  for line in (lines or [])]
        score, line = max(scored, default=(0.0, None), key=lambda item: item[0])
        return line if score >= minimum else None

    def _portal_click_line(self, hwnd, line: dict, hold: float = 0.08) -> None:
        sx, sy = vision.ref_to_screen(hwnd, int(line["cx"]), int(line["cy"]))
        self._mouse.shuffle_click(sx, sy, hold=hold)

    def _portal_wait_line(self, hwnd, stop_event, wanted: str, timeout: float):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._checkpoint(stop_event):
                return None
            frame = vision.capture_game_bgr(hwnd)
            if frame is not None:
                line = self._portal_find_line(ocr_windows.ocr_lines(frame), wanted)
                if line is not None:
                    return line
            self._interruptible_sleep(0.25, stop_event)
        return None

    @staticmethod
    def _portal_text(lines: list) -> str:
        return "\n".join(line.get("text", "") for line in (lines or []))

    def _portal_inventory_candidates(self, lines: list, task: dict) -> list[dict]:
        wanted_name = task.get("map") or "Any Portal"
        wanted_tier = str(task.get("portal_tier") or "Any")
        portal_lines = []
        for line in lines or []:
            # Inventory cards occupy the upper-left/centre portion. Excluding
            # the detail pane prevents its large repeated title becoming a
            # second candidate for the selected card.
            if line.get("cx", 9999) > 700 or line.get("cy", 9999) > 390:
                continue
            name = portal.portal_name_from_text(line.get("text", ""))
            if name is None:
                continue
            if wanted_name != "Any Portal" and name != wanted_name:
                continue
            portal_lines.append((line, name))

        tier_lines = [line for line in (lines or []) if portal.tier_from_text(line.get("text", ""))]
        candidates = []
        for line, name in portal_lines:
            above = [tier_line for tier_line in tier_lines
                     if 0 <= line["cy"] - tier_line["cy"] <= 170
                     and abs(line["cx"] - tier_line["cx"]) <= 100]
            tier_line = min(above, default=None,
                            key=lambda item: abs(line["cx"] - item["cx"]) +
                            abs(line["cy"] - item["cy"]))
            tier = portal.tier_from_text(tier_line.get("text", "")) if tier_line else None
            if wanted_tier != "Any" and tier != wanted_tier:
                continue
            candidates.append({
                "name": name,
                "tier": tier,
                "x": int(line["cx"]),
                "y": max(80, int(line["cy"]) - 55),
            })
        return candidates

    def _portal_scan_owned(self, hwnd, stop_event, task: dict) -> list[dict]:
        frame = vision.capture_game_bgr(hwnd)
        if frame is None:
            return []
        lines = ocr_windows.ocr_lines(frame)
        candidates = self._portal_inventory_candidates(lines, task)
        scanned = []
        for candidate in candidates:
            if self._checkpoint(stop_event):
                break
            self._click_ref(hwnd, candidate["x"], candidate["y"], hold=0.08)
            self._interruptible_sleep(PORTAL_CARD_SETTLE, stop_event)
            detail = vision.capture_game_bgr(hwnd)
            detail_lines = ocr_windows.ocr_lines(detail) if detail is not None else []
            modifiers = portal.modifiers_from_text(self._portal_text(detail_lines))
            scanned.append({
                **candidate,
                "modifiers": modifiers,
                "modifiers_readable": bool(modifiers) or not (
                    task.get("portal_preferred_modifiers") or
                    task.get("portal_avoided_modifiers")),
            })
        return scanned

    def _portal_choose_owned(self, hwnd, stop_event, task: dict,
                             activate_button: bool) -> bool:
        options = self._portal_scan_owned(hwnd, stop_event, task)
        choice = portal.choose_portal(
            options,
            task.get("portal_preferred_modifiers"),
            task.get("portal_avoided_modifiers"),
            require_safe=True,
        )
        if choice is None:
            self._log("[Portal] No owned portal matched the selected name/tier without an avoided "
                      "modifier. Nothing unsafe was activated.")
            return False
        self._log(f'[Portal] Selected {choice["name"]} Tier {choice.get("tier") or "?"} '
                  f'with modifiers: {", ".join(choice["modifiers"]) or "none read"}.')
        self._click_ref(hwnd, choice["x"], choice["y"], hold=0.08)
        self._interruptible_sleep(PORTAL_CARD_SETTLE, stop_event)
        if not activate_button:
            return True
        activate = self._portal_wait_line(
            hwnd, stop_event, "Activate Portal", PORTAL_ACTIVATE_TIMEOUT)
        if activate is None:
            self._log('[Portal] "Activate Portal" did not appear after selecting the portal.')
            return False
        self._portal_click_line(hwnd, activate)
        return True

    def _portal_activate_from_lobby(self, hwnd, stop_event, task: dict,
                                    webhook: dict = None) -> bool:
        if not self._ensure_lobby(hwnd, stop_event):
            return False
        self._set_status(action="Opening Portal inventory...")
        wm.activate_window(hwnd)
        self._keyboard.tap(ord("J"))
        portals = self._portal_wait_line(hwnd, stop_event, "Portals", PORTAL_MENU_TIMEOUT)
        if portals is None:
            self._log('[Portal] Items did not open with J, or the Portals tab was not readable.')
            return False
        self._portal_click_line(hwnd, portals)
        if self._portal_wait_line(hwnd, stop_event, "Activate Portal", PORTAL_MENU_TIMEOUT) is None:
            self._log('[Portal] The new Portals inventory tab did not finish opening.')
            return False
        if not self._portal_choose_owned(hwnd, stop_event, task, activate_button=True):
            return False
        self._set_status(action="Activating portal...")
        return self._wait_teleport_in(hwnd, stop_event, webhook, task)

    def _portal_select_from_victory(self, hwnd, stop_event, task: dict) -> bool:
        select_line = self._portal_wait_line(
            hwnd, stop_event, "Select Portal", PORTAL_MENU_TIMEOUT)
        if select_line is None:
            self._log('[Portal] Victory did not show the "Select Portal" button.')
            return False
        self._portal_click_line(hwnd, select_line)
        if self._portal_wait_line(hwnd, stop_event, "Portal Selection", PORTAL_MENU_TIMEOUT) is None:
            self._log("[Portal] Portal Selection did not open after Victory.")
            return False
        if not self._portal_choose_owned(hwnd, stop_event, task, activate_button=False):
            return False
        # Some versions select immediately; others expose the same Activate
        # button as Items. Click it when present without requiring it.
        activate = self._portal_wait_line(hwnd, stop_event, "Activate Portal", 1.0)
        if activate is not None:
            self._portal_click_line(hwnd, activate)
        return True

    def _portal_pick_reward_if_visible(self, hwnd, stop_event, task: dict) -> bool:
        """Inspect and choose one of the three forced portal reward cards."""
        now = time.monotonic()
        if now - getattr(self, "_portal_last_reward_scan", 0.0) < PORTAL_REWARD_SCAN_INTERVAL:
            return False
        self._portal_last_reward_scan = now
        frame = vision.capture_game_bgr(hwnd)
        if frame is None:
            return False
        lines = ocr_windows.ocr_lines(frame)
        text = self._portal_text(lines)
        if (self._portal_find_line(lines, "Auto-selecting", 0.65) is None
                and "auto selecting" not in re.sub(r"[^a-z ]", " ", text.lower())):
            return False

        self._set_status(action="Choosing portal reward by modifiers...")
        options = []
        for index, (x, y) in enumerate(PORTAL_REWARD_CARD_CENTERS):
            if self._checkpoint(stop_event):
                return True
            sx, sy = vision.ref_to_screen(hwnd, x, y)
            self._mouse.move_to(sx, sy)
            self._interruptible_sleep(PORTAL_CARD_SETTLE, stop_event)
            hovered = vision.capture_game_bgr(hwnd)
            hover_lines = ocr_windows.ocr_lines(hovered) if hovered is not None else []
            hover_text = self._portal_text(hover_lines)
            options.append({
                "index": index,
                "x": x,
                "y": y,
                "name": portal.portal_name_from_text(hover_text),
                "tier": portal.tier_from_text(hover_text),
                "modifiers": portal.modifiers_from_text(hover_text),
                "modifiers_readable": True,
            })
        choice = portal.choose_portal(
            options,
            task.get("portal_preferred_modifiers"),
            task.get("portal_avoided_modifiers"),
            require_safe=False,
        )
        if choice is None:
            return False
        avoided = set(choice["modifiers"]) & set(portal.normalize_modifier_list(
            task.get("portal_avoided_modifiers")))
        if avoided:
            self._log("[Portal] Every reward offer contained an avoided modifier; choosing the "
                      f'least-bad card ({", ".join(sorted(avoided))}).')
        else:
            self._log("[Portal] Choosing reward card "
                      f'{choice["index"] + 1}: {", ".join(choice["modifiers"]) or "no modifier read"}.')
        self._click_ref(hwnd, choice["x"], choice["y"], hold=0.1)
        self._interruptible_sleep(0.5, stop_event)
        return True
