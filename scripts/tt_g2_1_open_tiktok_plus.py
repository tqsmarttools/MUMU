#!/usr/bin/env python3
"""
TT-G2.1 (TikTok - Stage 2 - Script 1)
1) Open TikTok Lite.
2) Tap the '+' create button with random jitter each run.
3) Tap the middle 'Video' tab with random jitter each run.
4) Tap a video thumbnail to enter edit screen.
5) Tap 'Next', auto fill caption/hashtags from product code, then stop at post screen.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import uiautomator2 as u2

PKG = "com.zhiliaoapp.musically.go"
DEFAULT_SERIAL = "127.0.0.1:16448"
RID_VIDEO_TAB = "com.zhiliaoapp.musically.go.df_edit_filter:id/f3l"
RID_FIRST_TILE = "com.zhiliaoapp.musically.go.df_edit_filter:id/dx8"
RID_NEXT_BTN = "com.zhiliaoapp.musically.go.df_edit_filter:id/exp"
DELAY_MULTIPLIER = 1.35
DEFAULT_CAPTION_CSV = r"D:\MUMU\scripts\data\caption_master.csv"
DEFAULT_CAPTION_JSON = r"D:\MUMU\scripts\data\caption_bank.json"
DEFAULT_CAPTION_HISTORY = r"D:\MUMU\scripts\state\caption_history.json"
DEFAULT_CAPTION_OUT = r"D:\MUMU\scripts\state\last_caption_pick.json"


def log(msg: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def human_sleep(min_s: float, max_s: float | None = None) -> None:
    if max_s is None:
        sec = min_s
    else:
        sec = random.uniform(min_s, max_s)
    sec = max(0.05, sec * DELAY_MULTIPLIER)
    time.sleep(sec)


def run_cmd(cmd: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout,
    )


def ensure_adb_ready(serial: str, timeout_sec: int = 90) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        cp = run_cmd(["adb", "devices"])
        state = None
        for line in cp.stdout.splitlines():
            if line.startswith(serial + "\t"):
                state = line.split("\t", 1)[1].strip()
                break

        if state == "device":
            return
        if state == "offline":
            run_cmd(["adb", "disconnect", serial], timeout=10)
        run_cmd(["adb", "connect", serial], timeout=10)
        human_sleep(1.8, 2.4)

    raise RuntimeError(f"ADB not ready for {serial}")


def connect_device_with_retry(serial: str, max_retries: int = 3) -> u2.Device:
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            ensure_adb_ready(serial, timeout_sec=120)
            d = u2.connect(serial)
            d.implicitly_wait(2)
            d.screen_on()
            return d
        except Exception as exc:
            last_exc = exc
            log(f"connect attempt {attempt}/{max_retries} failed: {exc}")
            try:
                run_cmd(["adb", "disconnect", serial], timeout=8)
            except Exception as disconnect_exc:
                log(f"adb disconnect warning: {disconnect_exc}")
            try:
                run_cmd(["adb", "kill-server"], timeout=8)
            except Exception as kill_exc:
                log(f"adb kill-server warning: {kill_exc}")
            try:
                run_cmd(["adb", "start-server"], timeout=12)
            except Exception as start_exc:
                log(f"adb start-server warning: {start_exc}")
            try:
                run_cmd(["adb", "connect", serial], timeout=12)
            except Exception as connect_exc:
                log(f"adb connect warning: {connect_exc}")
            human_sleep(1.8, 3.0)

    raise RuntimeError(f"Cannot connect device {serial}: {last_exc}")


def wait_package_foreground(
    d: u2.Device,
    package: str,
    timeout_sec: float = 10.0,
    stable_sec: float = 1.0,
) -> bool:
    deadline = time.time() + timeout_sec
    stable_from: float | None = None
    while time.time() < deadline:
        current = d.app_current()
        if current.get("package", "") == package:
            if stable_from is None:
                stable_from = time.time()
            elif (time.time() - stable_from) >= stable_sec:
                return True
        else:
            stable_from = None
        human_sleep(0.22, 0.35)
    return False


def open_tiktok(d: u2.Device) -> None:
    for attempt in range(1, 4):
        log(f"open app: {PKG} ({attempt}/3)")
        try:
            d.app_start(PKG, use_monkey=False)
        except Exception:
            pass
        human_sleep(0.7, 1.2)
        if wait_package_foreground(d, PKG, timeout_sec=10.0, stable_sec=1.2):
            # Give app extra settle time after foreground to reduce immediate crash/exit spikes.
            human_sleep(2.6, 3.8)
            return

        # Fallback launcher intent trigger when direct app_start is not foregrounding app.
        try:
            d.shell(f"monkey -p {PKG} -c android.intent.category.LAUNCHER 1")
        except Exception:
            pass
        if wait_package_foreground(d, PKG, timeout_sec=8.0, stable_sec=1.2):
            human_sleep(2.6, 3.8)
            return

        try:
            d.app_stop(PKG)
        except Exception:
            pass
        human_sleep(0.8, 1.3)

    current = d.app_current()
    raise RuntimeError(
        "Cannot foreground TikTok after launch retries: "
        f"pkg={current.get('package','')} act={current.get('activity','')}"
    )


def is_tiktok_home(d: u2.Device) -> bool:
    current = d.app_current()
    return current.get("package", "") == PKG and current.get("activity", "") == ".mini.MainActivity"


def wait_tiktok_home_stable(
    d: u2.Device,
    timeout_sec: float = 10.0,
    stable_sec: float = 1.4,
) -> bool:
    deadline = time.time() + timeout_sec
    stable_from: float | None = None
    while time.time() < deadline:
        if is_tiktok_home(d):
            if stable_from is None:
                stable_from = time.time()
            elif (time.time() - stable_from) >= stable_sec:
                return True
        else:
            stable_from = None
        human_sleep(0.18, 0.28)
    return False


def ensure_tiktok_home(d: u2.Device, max_back_presses: int = 6) -> None:
    # Normalize start state so '+' tap always happens on TikTok home feed.
    open_tiktok(d)
    if wait_tiktok_home_stable(d, timeout_sec=7.0, stable_sec=1.4):
        return

    for _ in range(max_back_presses):
        if is_tiktok_home(d) and wait_tiktok_home_stable(d, timeout_sec=2.8, stable_sec=1.1):
            return

        current = d.app_current()
        package = current.get("package", "")
        activity = current.get("activity", "")

        if package != PKG:
            open_tiktok(d)
            continue

        # Only use Back for known in-app stacks. For unknown/transient activities,
        # relaunch is safer than accidental exit to launcher.
        if is_creation_screen(d) or is_video_picker_screen(d) or is_edit_screen(d) or is_post_screen(d):
            d.press("back")
            human_sleep(1.0, 1.6)
            continue

        log(f"home not stable yet, relaunch instead of back: pkg={package} act={activity}")
        d.app_stop(PKG)
        human_sleep(0.8, 1.3)
        open_tiktok(d)

    if not is_tiktok_home(d):
        for relaunch_attempt in range(1, 4):
            d.app_stop(PKG)
            human_sleep(0.8, 1.4)
            open_tiktok(d)
            if wait_tiktok_home_stable(d, timeout_sec=7.5, stable_sec=1.3):
                log(f"home recovery success after relaunch {relaunch_attempt}/3")
                return
            current = d.app_current()
            log(
                "home recovery relaunch not ready: "
                f"{relaunch_attempt}/3 pkg={current.get('package','')} act={current.get('activity','')}"
            )

        current = d.app_current()
        raise RuntimeError(
            "Cannot reach TikTok home before flow: "
            f"pkg={current.get('package','')} act={current.get('activity','')}"
        )


def is_creation_screen(d: u2.Device) -> bool:
    current = d.app_current()
    package = current.get("package", "")
    activity = current.get("activity", "")
    if package != PKG:
        return False

    if "CreationActivity" in activity or "creativetool" in activity.lower():
        return True
    return False


def is_gallery_screen(d: u2.Device) -> bool:
    current = d.app_current()
    package = current.get("package", "")
    activity = current.get("activity", "")
    return package == "com.android.gallery3d" or "GalleryActivity" in activity


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def bounds_from_info(info: dict) -> tuple[int, int, int, int]:
    b = info.get("bounds", {}) if isinstance(info, dict) else {}
    left = int(b.get("left", 0))
    top = int(b.get("top", 0))
    right = int(b.get("right", 0))
    bottom = int(b.get("bottom", 0))
    return left, top, right, bottom


def parse_bounds_str(bounds: str) -> tuple[int, int, int, int] | None:
    try:
        left_top, right_bottom = bounds.split("][")
        left_top = left_top.strip("[")
        right_bottom = right_bottom.strip("]")
        left, top = left_top.split(",")
        right, bottom = right_bottom.split(",")
        return int(left), int(top), int(right), int(bottom)
    except Exception:
        return None


def get_plus_bounds_from_bottom_nav(d: u2.Device) -> tuple[int, int, int, int] | None:
    """
    Resolve the center bottom '+' tab by reading the 5 bottom FrameLayout tabs
    and selecting the middle one. This is more stable than a fixed coordinate.
    """
    try:
        w, h = d.window_size()
        xml = d.dump_hierarchy()
        root = ET.fromstring(xml)
        tabs: list[tuple[int, int, int, int]] = []
        for node in root.iter("node"):
            if node.attrib.get("clickable", "false") != "true":
                continue
            if node.attrib.get("class", "") != "android.widget.FrameLayout":
                continue
            b = parse_bounds_str(node.attrib.get("bounds", ""))
            if not b:
                continue
            left, top, right, bottom = b
            if top < int(h * 0.85):
                continue
            # Ignore tiny/non-tab frame layouts.
            if (right - left) < int(w * 0.12) or (bottom - top) < int(h * 0.04):
                continue
            tabs.append((left, top, right, bottom))

        if len(tabs) < 3:
            return None
        tabs.sort(key=lambda t: (t[0] + t[2]) // 2)
        return tabs[len(tabs) // 2]
    except Exception:
        return None


def wait_plus_tab_ready(d: u2.Device, timeout_sec: float = 7.0, stable_sec: float = 0.9) -> tuple[int, int, int, int] | None:
    deadline = time.time() + timeout_sec
    last_bounds: tuple[int, int, int, int] | None = None
    stable_from: float | None = None
    while time.time() < deadline:
        b = get_plus_bounds_from_bottom_nav(d)
        if b is None:
            last_bounds = None
            stable_from = None
            human_sleep(0.22, 0.34)
            continue
        if b != last_bounds:
            last_bounds = b
            stable_from = time.time()
        elif stable_from is not None and (time.time() - stable_from) >= stable_sec:
            return b
        human_sleep(0.20, 0.32)
    return last_bounds


def tap_plus_random(
    d: u2.Device,
    base_x_ratio: float = 0.50,
    base_y_ratio: float = 0.92,
    max_attempts: int = 4,
) -> None:
    w, h = d.window_size()
    base_x = int(round(w * base_x_ratio))
    base_y = int(round(h * base_y_ratio))
    plus_bounds = wait_plus_tab_ready(d, timeout_sec=5.5, stable_sec=0.8)
    if plus_bounds is not None:
        left, top, right, bottom = plus_bounds
        base_x = (left + right) // 2
        # Prefer upper area of center tab to avoid bottom gesture/nav zone.
        base_y = top + int((bottom - top) * 0.28)

    for attempt in range(1, max_attempts + 1):
        current = d.app_current()
        if current.get("package", "") != PKG:
            log(
                "left TikTok while tapping '+', recovering in-app: "
                f"pkg={current.get('package','')} act={current.get('activity','')}"
            )
            open_tiktok(d)
            human_sleep(0.8, 1.3)
            continue

        if is_creation_screen(d):
            log("create screen opened")
            return

        if not wait_tiktok_home_stable(d, timeout_sec=4.8, stable_sec=1.5):
            log("home not stable before '+' tap, re-sync to home")
            ensure_tiktok_home(d, max_back_presses=3)
            if not wait_tiktok_home_stable(d, timeout_sec=7.0, stable_sec=1.8):
                continue

        # Extra settle window before touching '+'.
        human_sleep(1.6, 2.4)
        if not wait_tiktok_home_stable(d, timeout_sec=3.2, stable_sec=1.2):
            log("home unstable before '+' settle complete; retry '+' step")
            continue

        plus_bounds = wait_plus_tab_ready(d, timeout_sec=5.2, stable_sec=1.0)
        if plus_bounds is not None:
            left, top, right, bottom = plus_bounds
            base_x = (left + right) // 2
            base_y = top + int((bottom - top) * 0.28)
        else:
            # Do not fallback-tap when center tab is unresolved; resync then retry.
            if attempt < max_attempts:
                log("cannot resolve '+' tab bounds; resync home and retry")
                ensure_tiktok_home(d, max_back_presses=2)
                human_sleep(0.8, 1.3)
                continue
            raise RuntimeError("Cannot resolve '+' tab bounds on TikTok home")

        x = clamp(base_x, 1, max(1, w - 2))
        if plus_bounds is not None:
            left, top, right, bottom = plus_bounds
            # Lock Y into a very narrow safe band near top of center tab.
            safe_top = top + int((bottom - top) * 0.18)
            safe_bottom = top + int((bottom - top) * 0.36)
            y = clamp(base_y, safe_top, safe_bottom)
            x = clamp(x, left + 2, right - 2)
        log(f"tap '+' attempt {attempt}/{max_attempts} at ({x},{y})")
        d.click(x, y)
        # Two-phase wait to absorb delayed UI transitions.
        human_sleep(1.6, 2.4)
        if is_creation_screen(d):
            if wait_creation_ui_ready(d, timeout_sec=6.5):
                log("create screen opened and interactive")
                return
            log("create screen opened but UI not ready (black/loading); back and retry '+'")
            d.press("back")
            human_sleep(1.0, 1.6)
            continue
        human_sleep(1.0, 1.6)

        if is_creation_screen(d):
            if wait_creation_ui_ready(d, timeout_sec=4.5):
                log("create screen opened and interactive")
                return
            log("create screen still not interactive; back and retry '+'")
            d.press("back")
            human_sleep(1.0, 1.6)
            continue

        if is_gallery_screen(d):
            log("gallery opened after '+', back and retry")
            d.press("back")
            human_sleep(1.0, 1.8)
            if d.app_current().get("package", "") != PKG:
                open_tiktok(d)
                human_sleep(0.8, 1.4)
            continue

    raise RuntimeError("Cannot open create screen from '+' button")


def find_video_tab(d: u2.Device):
    selectors = [
        d(text="Video"),
        d(textMatches=r"(?i)^video$"),
        d(description="Video"),
        d(descriptionMatches=r"(?i)^video$"),
    ]
    for sel in selectors:
        if sel.exists:
            return sel
    return None


def normalize_tab_label(raw: str | None) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"\s+", "", text)
    return text


def get_media_tab_nodes(d: u2.Device) -> list[dict]:
    rows: list[dict] = []
    # Fast path: avoid heavy XML dump when UIAutomator selector is enough.
    try:
        items = d(resourceId=RID_VIDEO_TAB).all()
        for item in items:
            try:
                info = item.info or {}
            except Exception:
                continue
            text_raw = str(info.get("text", "") or "").strip()
            label = normalize_tab_label(text_raw)
            if label not in {"tatca", "video", "anh", "all", "photo"}:
                continue
            left, top, right, bottom = bounds_from_info(info)
            node_bounds = (left, top, right, bottom) if right > left and bottom > top else None
            rows.append(
                {
                    "label": label,
                    "text": text_raw,
                    "selected": bool(info.get("selected", False)),
                    "node_bounds": node_bounds,
                    "parent_bounds": None,
                }
            )
        if rows:
            rows.sort(
                key=lambda t: (
                    ((t.get("node_bounds") or (0, 0, 0, 0))[0] + (t.get("node_bounds") or (0, 0, 0, 0))[2]) // 2
                )
            )
            return rows
    except Exception:
        pass

    rows = []
    try:
        xml = d.dump_hierarchy()
        root = ET.fromstring(xml)
        parent_map: dict[int, ET.Element] = {}
        for p in root.iter("node"):
            for c in list(p):
                parent_map[id(c)] = p

        for node in root.iter("node"):
            rid = node.attrib.get("resource-id", "") or ""
            if not rid.endswith(":id/f3l"):
                continue
            text_raw = (node.attrib.get("text", "") or "").strip()
            label = normalize_tab_label(text_raw)
            if label not in {"tatca", "video", "anh", "all", "photo"}:
                continue
            n_bounds = parse_bounds_str(node.attrib.get("bounds", ""))
            p_bounds = None
            p = parent_map.get(id(node))
            if p is not None:
                p_bounds = parse_bounds_str(p.attrib.get("bounds", ""))
            rows.append(
                {
                    "label": label,
                    "text": text_raw,
                    "selected": (node.attrib.get("selected", "false").lower() == "true"),
                    "node_bounds": n_bounds,
                    "parent_bounds": p_bounds,
                }
            )
    except Exception:
        return []
    rows.sort(
        key=lambda t: (((t.get("node_bounds") or (0, 0, 0, 0))[0] + (t.get("node_bounds") or (0, 0, 0, 0))[2]) // 2)
    )
    return rows


def is_creation_ui_ready(d: u2.Device) -> bool:
    if not is_creation_screen(d):
        return False
    if d(resourceId=RID_VIDEO_TAB).exists:
        return True
    if d(resourceId=RID_FIRST_TILE).exists:
        return True
    if find_video_tab(d) is not None:
        return True
    tabs = get_media_tab_nodes(d)
    return len(tabs) >= 2


def wait_creation_ui_ready(d: u2.Device, timeout_sec: float = 6.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if is_creation_ui_ready(d):
            return True
        if not is_creation_screen(d):
            return False
        human_sleep(0.25, 0.40)
    return False


def is_video_tab_active(d: u2.Device) -> bool:
    tabs = get_media_tab_nodes(d)
    if tabs:
        for t in tabs:
            if t["label"] == "video" and t["selected"]:
                return True
        return False

    # Selector fallback when XML snapshot is unavailable.
    candidates = [d(textMatches=r"(?i)^video$", selected=True), d(descriptionMatches=r"(?i)^video$", selected=True)]
    for sel in candidates:
        try:
            if sel.exists:
                return True
        except Exception:
            continue
    return False


def tap_video_tab_random(
    d: u2.Device,
    jitter_x: int = 6,
    jitter_y: int = 4,
    max_attempts: int = 4,
) -> None:
    w, h = d.window_size()
    started_at = time.time()
    # Middle tab area on create picker.
    fallback_base_x = int(round(w * 0.50))
    fallback_base_y = int(round(h * 0.367))

    for attempt in range(1, max_attempts + 1):
        if (time.time() - started_at) > 22.0:
            raise RuntimeError("Video tab step timeout (possible black/frozen create screen)")
        if is_gallery_screen(d):
            log("gallery is foreground before tap 'Video'; back to TikTok create screen")
            d.press("back")
            human_sleep(1.2, 2.0)
            continue

        current = d.app_current()
        log(
            "video-tab check "
            f"attempt {attempt}/{max_attempts}: "
            f"pkg={current.get('package','')} act={current.get('activity','')}"
        )
        if current.get("package", "") != PKG:
            raise RuntimeError(
                "Left TikTok while opening Video tab: "
                f"pkg={current.get('package','')} act={current.get('activity','')}"
            )
        if current.get("activity", "") == ".mini.MainActivity":
            log("dropped to TikTok home while opening 'Video'; reopen create and retry")
            tap_plus_random(d, max_attempts=3)
            human_sleep(0.9, 1.4)
            continue

        if is_video_tab_active(d) and wait_first_video_tile_ready(d, timeout_sec=1.2):
            log("video picker already ready on 'Video' tab")
            return

        tab_nodes = get_media_tab_nodes(d)
        video_node = next((t for t in tab_nodes if t["label"] == "video"), None)

        if video_node is None:
            sel = find_video_tab(d)
            if sel is not None:
                try:
                    left, top, right, bottom = bounds_from_info(sel.info)
                    if right > left and bottom > top:
                        cx = (left + right) // 2
                        cy = (top + bottom) // 2
                        x = clamp(cx + random.randint(-jitter_x, jitter_x), left + 1, right - 1)
                        y = clamp(cy + random.randint(-jitter_y, jitter_y), top + 1, bottom - 1)
                        log(f"tap 'Video' selector attempt {attempt}/{max_attempts} at ({x},{y})")
                        d.click(x, y)
                        human_sleep(1.0, 1.7)
                        if is_video_tab_active(d) and wait_first_video_tile_ready(d, timeout_sec=2.2):
                            log("video selector accepted; 'Video' picker ready")
                            return
                except Exception:
                    pass

        if video_node is None:
            # Fallback: tap expected middle 'Video' tab zone with jitter.
            x = clamp(fallback_base_x + random.randint(-jitter_x, jitter_x), 1, max(1, w - 2))
            y = clamp(fallback_base_y + random.randint(-jitter_y, jitter_y), 1, max(1, h - 2))
            log(f"tap 'Video' fallback attempt {attempt}/{max_attempts} at ({x},{y})")
            d.click(x, y)
            human_sleep(0.9, 1.5)
            if is_video_tab_active(d) and wait_first_video_tile_ready(d, timeout_sec=2.2):
                log("video tab fallback accepted; 'Video' picker ready")
                return
            continue

        vb = video_node.get("parent_bounds") or video_node.get("node_bounds")
        if not vb:
            vb = (int(w * 0.34), int(h * 0.33), int(w * 0.66), int(h * 0.41))
        left, top, right, bottom = vb

        if right <= left or bottom <= top:
            x = clamp(fallback_base_x + random.randint(-jitter_x, jitter_x), 1, max(1, w - 2))
            y = clamp(fallback_base_y + random.randint(-jitter_y, jitter_y), 1, max(1, h - 2))
            log(f"tap 'Video' bounds fallback attempt {attempt}/{max_attempts} at ({x},{y})")
            d.click(x, y)
            human_sleep(1.0, 1.6)
            if is_video_tab_active(d) and wait_first_video_tile_ready(d, timeout_sec=2.2):
                log("video bounds fallback accepted; 'Video' picker ready")
                return
            continue

        cx = (left + right) // 2
        cy = (top + bottom) // 2
        x = clamp(cx + random.randint(-jitter_x, jitter_x), left + 1, right - 1)
        y = clamp(cy + random.randint(-jitter_y, jitter_y), top + 1, bottom - 1)
        log(f"tap 'Video' attempt {attempt}/{max_attempts} at ({x},{y})")
        d.click(x, y)
        human_sleep(1.1, 1.8)
        if is_video_tab_active(d) and wait_first_video_tile_ready(d, timeout_sec=2.4):
            log("video tab tapped successfully; 'Video' picker ready")
            return

    # Last-resort safety: only continue when picker indicators are still visible.
    if is_video_tab_active(d) and wait_first_video_tile_ready(d, timeout_sec=1.8):
        log("video tab selector drift; continue because video picker is still visible")
        return

    current = d.app_current()
    raise RuntimeError(
        "Cannot find/tap 'Video' tab: "
        f"pkg={current.get('package','')} act={current.get('activity','')}"
    )


def is_video_picker_screen(d: u2.Device) -> bool:
    current = d.app_current()
    package = current.get("package", "")
    activity = current.get("activity", "")
    if package != PKG:
        return False
    if "CreationActivity" not in activity and "creativetool" not in activity.lower():
        return False
    if not is_video_tab_active(d):
        return False
    # Strict picker markers only (avoid false-positive from status-bar clock/home feed text).
    if d(resourceId=RID_VIDEO_TAB).exists:
        return True
    return False


def wait_first_video_tile_ready(d: u2.Device, timeout_sec: float = 7.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not is_video_picker_screen(d):
            human_sleep(0.25, 0.40)
            continue

        tile = d(resourceId=RID_FIRST_TILE)
        if tile.exists:
            try:
                left, top, right, bottom = bounds_from_info(tile.info)
                if (right - left) > 24 and (bottom - top) > 24:
                    return True
            except Exception:
                return True
        human_sleep(0.25, 0.45)
    return False


def wait_edit_screen_stable(
    d: u2.Device,
    timeout_sec: float = 5.0,
    stable_sec: float = 0.9,
) -> bool:
    deadline = time.time() + timeout_sec
    stable_from: float | None = None
    while time.time() < deadline:
        current = d.app_current()
        if (
            current.get("package", "") == PKG
            and current.get("activity", "") != ".mini.MainActivity"
            and is_edit_screen(d)
        ):
            if stable_from is None:
                stable_from = time.time()
            elif (time.time() - stable_from) >= stable_sec:
                return True
        else:
            stable_from = None
        human_sleep(0.22, 0.36)
    return False


def click_next_button_strict(d: u2.Device) -> bool:
    # Prefer direct selector click on known Next button.
    selectors = [
        d(resourceId=RID_NEXT_BTN),
        d(text="Ti\u1ebfp"),
        d(textMatches=r"(?i)^ti(?:\u1ebfp|ep)$"),
        d(text="Next"),
        d(textMatches=r"(?i)^next$"),
    ]
    for sel in selectors:
        try:
            if sel.exists:
                if sel.click_exists(timeout=1.2):
                    return True
                # Fallback on exact center of selector bounds (no jitter).
                left, top, right, bottom = bounds_from_info(sel.info)
                if right > left and bottom > top:
                    d.click((left + right) // 2, (top + bottom) // 2)
                    return True
        except Exception:
            continue

    # XML fallback: locate visible 'Tiếp' / 'Next' button node and tap center.
    try:
        xml = d.dump_hierarchy()
        root = ET.fromstring(xml)
        for node in root.iter("node"):
            label = normalize_tab_label(node.attrib.get("text", ""))
            if label not in {"tiep", "next"}:
                continue
            b = parse_bounds_str(node.attrib.get("bounds", ""))
            if not b:
                continue
            left, top, right, bottom = b
            if right > left and bottom > top:
                d.click((left + right) // 2, (top + bottom) // 2)
                return True
    except Exception:
        pass
    return False


def is_edit_screen(d: u2.Device) -> bool:
    if d(resourceId=RID_NEXT_BTN).exists:
        return True
    if d(textMatches=r"(?i)^ti(?:\u1ebfp|ep)$").exists:
        return True
    if d(text="Ti\u1ebfp").exists or d(text="Next").exists:
        return True
    return False


def is_post_screen(d: u2.Device) -> bool:
    if d(textMatches=r".*M\u00f4 t\u1ea3 video.*").exists:
        return True
    if d(textMatches=r"(?i).*hashtag.*").exists:
        return True
    if d(textMatches=r".*B\u1ea3n nh\u00e1p.*").exists:
        return True
    if d(textMatches=r".*\u0110\u0103ng.*").exists:
        return True
    if d(textMatches=r".*\u0103ng.*").exists:
        return True
    return False


def normalize_video_hint(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = re.sub(r"\s+", " ", str(raw)).strip()
    if not text:
        return None
    if text.lower() in {"video", "photo", "anh", "\u1ea3nh"}:
        return None
    # Ignore pure duration strings such as "00:15".
    if re.fullmatch(r"\d{1,2}:\d{2}", text):
        return None
    if len(text) < 3:
        return None
    return text


def detect_first_video_name_hint(d: u2.Device) -> str | None:
    candidates: list[str] = []

    def add_candidate(raw: str | None) -> None:
        c = normalize_video_hint(raw)
        if c and c not in candidates:
            candidates.append(c)

    tile = d(resourceId=RID_FIRST_TILE)
    if tile.exists:
        try:
            info = tile.info or {}
            add_candidate(str(info.get("contentDescription", "") or ""))
            add_candidate(str(info.get("description", "") or ""))
            add_candidate(str(info.get("text", "") or ""))
        except Exception:
            pass

    try:
        xml = d.dump_hierarchy()
        root = ET.fromstring(xml)
        for node in root.iter("node"):
            if node.attrib.get("resource-id", "") != RID_FIRST_TILE:
                continue
            add_candidate(node.attrib.get("content-desc", ""))
            add_candidate(node.attrib.get("text", ""))
            break
    except Exception:
        pass

    if not candidates:
        return None

    # Prefer candidate that looks like a filename/code token.
    for c in candidates:
        uc = c.upper()
        if any(x in uc for x in [".MP4", ".MOV", ".M4V", ".MKV", ".AVI"]):
            return c
        if re.search(r"[A-Z]{2,}\d*[-_]", uc) or re.search(r"\d{4,}[-_][A-Z0-9]{2,}", uc):
            return c
    return candidates[0]


def detect_latest_video_name_from_device(d: u2.Device) -> str | None:
    candidate_dirs = [
        "/sdcard/DCIM/Camera",
        "/storage/emulated/0/DCIM/Camera",
        "/sdcard/Movies/Upload",
        "/storage/emulated/0/Movies/Upload",
    ]
    allowed_ext = (".mp4", ".mov", ".m4v", ".mkv", ".avi")

    for folder in candidate_dirs:
        try:
            result = d.shell(f"ls -t {folder}")
            raw = str(result.output or "")
        except Exception:
            continue

        for line in raw.splitlines():
            name = line.strip()
            if not name:
                continue
            low = name.lower()
            if low.endswith(allowed_ext):
                hint = normalize_video_hint(name)
                if hint:
                    return hint
    return None


def pick_caption_payload(
    *,
    video_name_hint: str | None,
    product_code: str | None,
    caption_csv: str,
    caption_json: str,
    caption_history: str,
    strict_code: bool,
    recent_window: int,
    min_hashtags: int,
    max_hashtags: int,
    max_chars: int,
) -> dict:
    try:
        from caption_bank_tool import ensure_bank_ready, pick_caption
    except Exception as exc:
        raise RuntimeError(f"cannot import caption_bank_tool.py: {exc}") from exc

    csv_path = Path(caption_csv)
    json_path = Path(caption_json)
    history_path = Path(caption_history)

    ensure_bank_ready(csv_path=csv_path, json_path=json_path, auto_build_if_stale=True)
    payload = pick_caption(
        bank_path=json_path,
        history_path=history_path,
        product_code=product_code,
        video_name=video_name_hint,
        strict_code=strict_code,
        recent_window=recent_window,
        min_hashtags=min_hashtags,
        max_hashtags=max_hashtags,
        max_chars=max_chars,
    )
    return payload


def find_caption_field(d: u2.Device):
    selectors = [
        d(className="android.widget.EditText", focused=True),
        d(textMatches=r".*M\u00f4 t\u1ea3 b\u00e0i \u0111\u0103ng.*"),
        d(textMatches=r".*M\u00f4 t\u1ea3 video.*"),
        d(textMatches=r".*Vi\u1ebft m\u00f4 t\u1ea3.*"),
        d(descriptionMatches=r".*M\u00f4 t\u1ea3.*"),
        d(textMatches=r"(?i).*describe.*post.*"),
        d(resourceIdMatches=r"(?i).*(caption|desc|description|title).*"),
        d(className="android.widget.EditText"),
    ]
    for sel in selectors:
        if sel.exists:
            return sel
    return None


def fill_post_caption(
    d: u2.Device,
    final_text: str,
    max_attempts: int = 4,
) -> None:
    text = (final_text or "").strip()
    if not text:
        log("caption text is empty; skip fill")
        return

    if not is_post_screen(d):
        raise RuntimeError("not on post screen while filling caption")

    for attempt in range(1, max_attempts + 1):
        current = d.app_current()
        if current.get("package", "") != PKG:
            raise RuntimeError(
                "Left TikTok while filling caption: "
                f"pkg={current.get('package','')} act={current.get('activity','')}"
            )

        field = find_caption_field(d)
        if field is None:
            w, h = d.window_size()
            # Fallback tap points for TikTok post caption box area.
            fallback_points = [
                (0.50, 0.36),
                (0.50, 0.31),
                (0.43, 0.38),
            ]
            ratio_x, ratio_y = fallback_points[(attempt - 1) % len(fallback_points)]
            fx = int(round(w * ratio_x))
            fy = int(round(h * ratio_y))
            log(f"caption field not found, tap fallback area attempt {attempt}/{max_attempts} at ({fx},{fy})")
            d.click(fx, fy)
            human_sleep(0.8, 1.3)
            try:
                d.send_keys(text, clear=True)
                human_sleep(0.7, 1.1)
                log(f"caption filled by fallback send_keys attempt {attempt}/{max_attempts}")
                return
            except Exception:
                pass
            continue

        try:
            field.click()
        except Exception:
            pass
        human_sleep(0.5, 1.0)

        set_ok = False
        try:
            field.set_text(text)
            set_ok = True
        except Exception:
            set_ok = False

        if not set_ok:
            try:
                d.send_keys(text, clear=True)
                set_ok = True
            except Exception:
                set_ok = False

        human_sleep(0.7, 1.2)
        if not set_ok:
            continue

        # Verify a meaningful token exists on screen after setting text.
        verify_token = text.splitlines()[0].strip().split(" ")
        probe = verify_token[0] if verify_token else ""
        if probe and d(textContains=probe[: min(20, len(probe))]).exists:
            log(f"caption filled successfully on attempt {attempt}/{max_attempts}")
            return

        # Secondary success condition: still at post screen and edit field focused.
        if is_post_screen(d) and d(className="android.widget.EditText").exists:
            log(f"caption likely filled (post screen stable) attempt {attempt}/{max_attempts}")
            return

    raise RuntimeError("cannot fill caption text on post screen")


def tap_first_video_random(
    d: u2.Device,
    jitter_x: int = 4,
    jitter_y: int = 6,
    max_attempts: int = 4,
) -> None:
    w, h = d.window_size()
    fallback_base_x = int(round(w * 0.167))
    fallback_base_y = int(round(h * 0.490))
    if not wait_first_video_tile_ready(d, timeout_sec=7.0):
        log("first video tile not ready after wait; continue with resilient picker taps")

    for attempt in range(1, max_attempts + 1):
        current = d.app_current()
        if current.get("package", "") != PKG:
            raise RuntimeError(
                "Left TikTok while selecting first video: "
                f"pkg={current.get('package','')} act={current.get('activity','')}"
            )
        if current.get("activity", "") == ".mini.MainActivity":
            log("dropped to TikTok home while selecting video; reopen create flow")
            ensure_tiktok_home(d, max_back_presses=3)
            tap_plus_random(d, max_attempts=3)
            tap_video_tab_random(d, jitter_x=6, jitter_y=4, max_attempts=3)
            human_sleep(0.9, 1.4)
            continue

        if is_post_screen(d):
            return
        if is_edit_screen(d):
            if wait_edit_screen_stable(d, timeout_sec=3.2, stable_sec=0.8):
                log("video edit screen already stable")
                return

        if not is_video_picker_screen(d):
            if is_creation_screen(d) and not is_gallery_screen(d):
                log("not yet on video picker, tap 'Video' again")
                tap_video_tab_random(d, jitter_x=6, jitter_y=4, max_attempts=2)
            human_sleep(0.8, 1.4)
            continue

        # Keep selection tight around the first video tile only.
        tile = d(resourceId=RID_FIRST_TILE)
        if tile.exists:
            try:
                left, top, right, bottom = bounds_from_info(tile.info)
                base_x = (left + right) // 2
                base_y = (top + bottom) // 2
                x = clamp(base_x + random.randint(-jitter_x, jitter_x), left + 1, right - 1)
                y = clamp(base_y + random.randint(-jitter_y, jitter_y), top + 1, bottom - 1)
            except Exception:
                x = clamp(fallback_base_x + random.randint(-jitter_x, jitter_x), 1, max(1, w - 2))
                y = clamp(fallback_base_y + random.randint(-jitter_y, jitter_y), 1, max(1, h - 2))
        else:
            x = clamp(fallback_base_x + random.randint(-jitter_x, jitter_x), 1, max(1, w - 2))
            y = clamp(fallback_base_y + random.randint(-jitter_y, jitter_y), 1, max(1, h - 2))

        # First try selector-level click with timeout when tile exists.
        if tile.exists:
            try:
                if tile.click_exists(timeout=1.8):
                    human_sleep(1.6, 2.8)
                    if is_post_screen(d):
                        return
                    if is_edit_screen(d) and wait_edit_screen_stable(d, timeout_sec=3.2, stable_sec=0.8):
                        log("video selected by selector click")
                        return
            except Exception:
                pass

        log(f"tap first video attempt {attempt}/{max_attempts} at ({x},{y})")
        d.click(x, y)
        human_sleep(0.55, 0.85)
        if not is_edit_screen(d) and not is_post_screen(d):
            # Some builds need a second tap to confirm video select.
            d.click(x, y)
        human_sleep(1.8, 2.9)
        if is_post_screen(d):
            log("video selected")
            return
        if is_edit_screen(d) and wait_edit_screen_stable(d, timeout_sec=3.2, stable_sec=0.8):
            log("video selected and edit screen stable")
            return

        # Nudge scroll when UI does not react, then re-check first tile visibility.
        sx = int(round(w * 0.50))
        d.swipe(sx, int(round(h * 0.66)), sx, int(round(h * 0.58)), 0.12)
        human_sleep(0.9, 1.4)

    # Final hard fallback on known first-tile center.
    hx = int(round(w * 0.167))
    hy = int(round(h * 0.490))
    log(f"tap first video hard fallback at ({hx},{hy})")
    d.click(hx, hy)
    human_sleep(0.55, 0.85)
    d.click(hx, hy)
    human_sleep(1.4, 2.3)
    if is_edit_screen(d) or is_post_screen(d):
        log("video selected by hard fallback")
        return

    raise RuntimeError("Cannot open video edit screen from picker")


def tap_next_to_post(
    d: u2.Device,
    max_attempts: int = 4,
) -> None:
    for attempt in range(1, max_attempts + 1):
        current = d.app_current()
        if current.get("package", "") != PKG:
            raise RuntimeError(
                "Left TikTok while opening post screen: "
                f"pkg={current.get('package','')} act={current.get('activity','')}"
            )
        if current.get("activity", "") == ".mini.MainActivity":
            if attempt < max_attempts:
                log("at TikTok home before 'Next'; reopen create flow and retry")
                ensure_tiktok_home(d, max_back_presses=3)
                tap_plus_random(d, max_attempts=3)
                tap_video_tab_random(d, jitter_x=6, jitter_y=4, max_attempts=3)
                tap_first_video_random(d, max_attempts=3)
                continue
            raise RuntimeError("Returned to TikTok home while opening post screen")

        if is_post_screen(d):
            log("already at post screen")
            return

        if not wait_edit_screen_stable(d, timeout_sec=2.8, stable_sec=0.8):
            log("edit screen not stable before tapping 'Next'; retrying step")
            human_sleep(0.8, 1.3)
            continue

        clicked = click_next_button_strict(d)
        if clicked:
            log(f"tap 'Next' attempt {attempt}/{max_attempts}")
        else:
            log(f"'Next' button not resolved attempt {attempt}/{max_attempts}; retry")
            human_sleep(0.9, 1.4)
            continue

        human_sleep(2.6, 3.8)
        current = d.app_current()
        if current.get("package", "") != PKG:
            raise RuntimeError(
                "Left TikTok after tapping Next: "
                f"pkg={current.get('package','')} act={current.get('activity','')}"
            )
        if current.get("activity", "") == ".mini.MainActivity" and not is_post_screen(d):
            if attempt < max_attempts:
                log("returned home after tapping 'Next'; reopen create flow and retry")
                ensure_tiktok_home(d, max_back_presses=3)
                tap_plus_random(d, max_attempts=3)
                tap_video_tab_random(d, jitter_x=6, jitter_y=4, max_attempts=3)
                tap_first_video_random(d, max_attempts=3)
                continue
            raise RuntimeError("Returned to TikTok home after tapping Next")
        if is_post_screen(d):
            log("post screen opened")
            return

    raise RuntimeError("Cannot open post screen after tapping 'Next'")


def is_expected_final_state(d: u2.Device) -> bool:
    current = d.app_current()
    package = current.get("package", "")
    activity = current.get("activity", "")
    if package != PKG:
        return False
    if is_post_screen(d):
        return True
    # Some app builds hide localized post labels while keyboard/IME is active.
    # Accept post-like state when not on home or edit screen and an EditText exists.
    if activity != ".mini.MainActivity" and (not is_edit_screen(d)) and d(className="android.widget.EditText").exists:
        return True
    return False


def main() -> int:
    global DELAY_MULTIPLIER
    parser = argparse.ArgumentParser(
        description=(
            "TT-G2.1: open TikTok, tap '+', tap 'Video', pick first video, tap 'Next', "
            "auto fill caption from product code, stop at post screen."
        )
    )
    parser.add_argument("--serial", default=DEFAULT_SERIAL, help="ADB serial")
    parser.add_argument("--max-attempts", type=int, default=4, help="Max retries to open create screen")
    parser.add_argument("--video-jitter-x", type=int, default=6, help="Horizontal jitter for 'Video' tab")
    parser.add_argument("--video-jitter-y", type=int, default=4, help="Vertical jitter for 'Video' tab")
    parser.add_argument("--video-max-attempts", type=int, default=4, help="Max retries to tap 'Video' tab")
    parser.add_argument("--pick-max-attempts", type=int, default=4, help="Max retries to pick a video from grid")
    parser.add_argument("--next-max-attempts", type=int, default=4, help="Max retries to tap 'Next'")
    parser.add_argument(
        "--fill-caption",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Auto fill caption/hashtags on post screen (default: enabled)",
    )
    parser.add_argument("--product-code", default=None, help="Optional explicit product code override (e.g. BCR)")
    parser.add_argument("--caption-csv", default=DEFAULT_CAPTION_CSV, help="Caption CSV source file")
    parser.add_argument("--caption-json", default=DEFAULT_CAPTION_JSON, help="Caption JSON bank file")
    parser.add_argument("--caption-history", default=DEFAULT_CAPTION_HISTORY, help="Caption anti-repeat history file")
    parser.add_argument(
        "--caption-out",
        default=DEFAULT_CAPTION_OUT,
        help="Optional picked caption payload output JSON file",
    )
    parser.add_argument(
        "--strict-caption-code",
        action="store_true",
        help="Fail when cannot resolve product code instead of fallback DEFAULT",
    )
    parser.add_argument("--caption-recent-window", type=int, default=5, help="Anti-repeat recent window per code")
    parser.add_argument("--caption-min-hashtags", type=int, default=2, help="Min hashtags to attach")
    parser.add_argument("--caption-max-hashtags", type=int, default=4, help="Max hashtags to attach")
    parser.add_argument("--caption-max-chars", type=int, default=1600, help="Hard cap of final caption text")
    parser.add_argument("--caption-fill-attempts", type=int, default=4, help="Retries to fill caption field")
    parser.add_argument(
        "--caption-required",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Fail full flow when caption cannot be filled (default: disabled)",
    )
    parser.add_argument("--final-recover-attempts", type=int, default=2, help="Number of full-flow retries on transient failures")
    parser.add_argument("--delay-multiplier", type=float, default=1.35, help="Human-like delay multiplier (higher = slower)")
    args = parser.parse_args()

    if args.video_jitter_x < 0 or args.video_jitter_y < 0:
        raise RuntimeError("video jitter values must be >= 0")
    if args.max_attempts <= 0:
        raise RuntimeError("--max-attempts must be > 0")
    if args.video_max_attempts <= 0:
        raise RuntimeError("--video-max-attempts must be > 0")
    if args.pick_max_attempts <= 0:
        raise RuntimeError("--pick-max-attempts must be > 0")
    if args.next_max_attempts <= 0:
        raise RuntimeError("--next-max-attempts must be > 0")
    if args.caption_recent_window <= 0:
        raise RuntimeError("--caption-recent-window must be > 0")
    if args.caption_min_hashtags < 0 or args.caption_max_hashtags < 0:
        raise RuntimeError("caption hashtag bounds must be >= 0")
    if args.caption_min_hashtags > args.caption_max_hashtags:
        raise RuntimeError("--caption-min-hashtags cannot be greater than --caption-max-hashtags")
    if args.caption_max_chars <= 0:
        raise RuntimeError("--caption-max-chars must be > 0")
    if args.caption_fill_attempts <= 0:
        raise RuntimeError("--caption-fill-attempts must be > 0")
    if args.final_recover_attempts < 0:
        raise RuntimeError("--final-recover-attempts must be >= 0")
    if args.delay_multiplier <= 0:
        raise RuntimeError("--delay-multiplier must be > 0")

    DELAY_MULTIPLIER = args.delay_multiplier
    log(f"delay multiplier: {DELAY_MULTIPLIER:.2f}")

    d = connect_device_with_retry(args.serial, max_retries=4)

    log(f"serial: {args.serial}")
    total_attempts = args.final_recover_attempts + 1
    last_exc: Exception | None = None
    for flow_attempt in range(1, total_attempts + 1):
        try:
            log(f"flow attempt {flow_attempt}/{total_attempts}")
            ensure_adb_ready(args.serial, timeout_sec=60)
            ensure_tiktok_home(d)
            tap_plus_random(
                d,
                max_attempts=args.max_attempts,
            )
            tap_video_tab_random(
                d,
                jitter_x=args.video_jitter_x,
                jitter_y=args.video_jitter_y,
                max_attempts=args.video_max_attempts,
            )
            video_name_hint = detect_first_video_name_hint(d)
            if video_name_hint:
                log(f"first video hint detected: {video_name_hint}")
            else:
                video_name_hint = detect_latest_video_name_from_device(d)
                if video_name_hint:
                    log(f"fallback latest-device video hint: {video_name_hint}")
                else:
                    log("video hint not detected; caption picker may fallback to DEFAULT")
            tap_first_video_random(
                d,
                max_attempts=args.pick_max_attempts,
            )
            tap_next_to_post(
                d,
                max_attempts=args.next_max_attempts,
            )
            if args.fill_caption:
                caption_payload = pick_caption_payload(
                    video_name_hint=video_name_hint,
                    product_code=args.product_code,
                    caption_csv=args.caption_csv,
                    caption_json=args.caption_json,
                    caption_history=args.caption_history,
                    strict_code=args.strict_caption_code,
                    recent_window=args.caption_recent_window,
                    min_hashtags=args.caption_min_hashtags,
                    max_hashtags=args.caption_max_hashtags,
                    max_chars=args.caption_max_chars,
                )
                caption_text = str(caption_payload.get("final_text", "") or "")
                caption_code = str(caption_payload.get("product_code", "") or "")
                log(
                    "caption picked: "
                    f"code={caption_code} id={caption_payload.get('caption_id','')} "
                    f"len={len(caption_text)}"
                )
                out_path = (args.caption_out or "").strip()
                if out_path:
                    p = Path(out_path)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(
                        json.dumps(caption_payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                try:
                    fill_post_caption(
                        d,
                        final_text=caption_text,
                        max_attempts=args.caption_fill_attempts,
                    )
                except Exception as caption_exc:
                    if args.caption_required:
                        raise
                    log(f"caption fill warning (non-fatal): {caption_exc}")
            if is_expected_final_state(d):
                break
            raise RuntimeError("Flow ended without post screen")
        except Exception as exc:
            last_exc = exc
            log(f"flow attempt {flow_attempt} failed: {exc}")
            if flow_attempt >= total_attempts:
                raise
            if "offline" in str(exc).lower():
                d = connect_device_with_retry(args.serial, max_retries=3)
            try:
                d.app_stop(PKG)
            except Exception:
                pass
            human_sleep(1.2, 2.0)

    if not is_expected_final_state(d):
        current = d.app_current()
        if last_exc is not None:
            raise RuntimeError(
                "Final state is not post screen after retries: "
                f"{last_exc} | pkg={current.get('package','')} act={current.get('activity','')}"
            )
        raise RuntimeError(
            "Final state is not post screen: "
            f"pkg={current.get('package','')} act={current.get('activity','')}"
        )

    log("final state confirmed at post screen (ready to tap 'Dang')")
    log("TT-G2.1 completed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log(f"FAILED: {exc}")
        sys.exit(1)
