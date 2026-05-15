#!/usr/bin/env python3
"""
TikTok Lite flow (PHONE_002):
1) Open TikTok and go to Home tab.
2) Open Search.
3) Pick one random keyword from:
   - bay xay dung
   - nem ke can bang
   - bay cat ron
   - mang keo rang cua
   - may khoan vit
4) Search keyword.
5) Scroll down 2 lines on search results.
6) Open the first visible video.
7) Wait current video to finish (best effort; fallback seconds).
8) Watch 3 more videos, each 5-10 seconds.
9) Go back to TikTok Home tab.
"""

from __future__ import annotations

import argparse
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import uiautomator2 as u2

PKG = "com.zhiliaoapp.musically.go"
DEFAULT_SERIAL = "127.0.0.1:16448"

KEYWORDS = [
    "bay xay dung",
    "nem ke can bang",
    "bay cat ron",
    "mang keo rang cua",
    "may khoan vit",
]


EXIT_OK = 0
EXIT_GENERIC_ERROR = 1
EXIT_DEVICE_ERROR = 2
EXIT_FLOW_ERROR = 3
DEFAULT_DELAY_MULTIPLIER = 1.2
DELAY_MULTIPLIER = DEFAULT_DELAY_MULTIPLIER
PRE_SEARCH_WARMUP_SWIPES = 1


class DevicePrepError(RuntimeError):
    """Raised when adb/device preparation cannot be completed."""


class FlowExecutionError(RuntimeError):
    """Raised when a UI flow still fails after retries/recovery."""


def log(msg: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def sleep_rand(lo: float = 1.0, hi: float = 1.7) -> None:
    lo_s = max(0.05, lo * DELAY_MULTIPLIER)
    hi_s = max(lo_s, hi * DELAY_MULTIPLIER)
    time.sleep(random.uniform(lo_s, hi_s))


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def run_cmd(cmd: list[str], check: bool = False, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout,
    )
    if check and cp.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)} | {(cp.stdout + cp.stderr).strip()}")
    return cp


def ensure_adb_ready(serial: str, timeout_sec: int = 90) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        cp = run_cmd(["adb", "devices"], check=False)
        state = None
        for line in cp.stdout.splitlines():
            if line.startswith(serial + "\t"):
                state = line.split("\t", 1)[1].strip()
                break

        if state == "device":
            return
        if state == "offline":
            run_cmd(["adb", "disconnect", serial], check=False)

        run_cmd(["adb", "connect", serial], check=False, timeout=10)
        time.sleep(2)
    raise DevicePrepError(f"ADB not ready for {serial}")


def preflight_check(serial: str) -> None:
    adb_path = shutil.which("adb")
    if not adb_path:
        raise DevicePrepError("adb not found in PATH")

    try:
        import uiautomator2 as _u2  # noqa: F401
    except Exception as exc:
        raise DevicePrepError(
            "Missing dependency 'uiautomator2'. Install with: "
            f"{sys.executable} -m pip install uiautomator2"
        ) from exc

    log(f"python: {sys.executable}")
    log(f"adb: {adb_path}")
    log(f"serial target: {serial}")


def handle_anr_dialog(d: u2.Device) -> bool:
    # Android ANR dialog selectors.
    anr_exists = (
        d(resourceId="android:id/alertTitle").exists
        or d(resourceId="android:id/aerr_wait").exists
        or d(resourceId="android:id/aerr_close").exists
        or d(textMatches=r"(?i)(kh\u00f4ng ph\u1ea3n h\u1ed3i|not responding|isn't responding)").exists
    )
    if not anr_exists:
        return False

    log("ANR popup detected, trying recover.")

    for sel in [
        d(resourceId="android:id/aerr_wait"),
        d(textMatches=r"(?i)(\u0111\u1ee3i|wait)"),
        d(descriptionMatches=r"(?i)(\u0111\u1ee3i|wait)"),
    ]:
        if sel.exists:
            sel.click()
            sleep_rand(1.2, 2.0)
            break

    if not (
        d(resourceId="android:id/aerr_wait").exists
        or d(textMatches=r"(?i)(kh\u00f4ng ph\u1ea3n h\u1ed3i|not responding|isn't responding)").exists
    ):
        return True

    for sel in [
        d(resourceId="android:id/aerr_close"),
        d(textMatches=r"(?i)(\u0111\u00f3ng \u1ee9ng d\u1ee5ng|close app|force close)"),
    ]:
        if sel.exists:
            sel.click()
            sleep_rand(1.0, 1.8)
            break

    return True


def current_package(d: u2.Device) -> str:
    try:
        return d.app_current().get("package", "")
    except Exception:
        return ""


def ensure_tiktok_context(d: u2.Device, context: str) -> None:
    pkg = current_package(d)
    if pkg != PKG:
        raise RuntimeError(f"{context}: expected package={PKG}, current={pkg or 'unknown'}")


def ensure_app_front(d: u2.Device, package_name: str = PKG, retries: int = 3) -> None:
    for attempt in range(1, retries + 1):
        handle_anr_dialog(d)
        cur = current_package(d)
        if cur == package_name:
            return

        log(f"ensure_app_front: bring app front attempt {attempt}/{retries} (current={cur or 'unknown'})")
        d.app_start(package_name, use_monkey=True)
        pid = d.app_wait(package_name, timeout=20, front=True)
        sleep_rand(1.2, 2.0)
        cur = current_package(d)
        if pid and cur == package_name:
            return

    final_pkg = current_package(d)
    raise RuntimeError(
        f"Cannot bring app to foreground: expected package={package_name}, current={final_pkg or 'unknown'}"
    )


def stabilize_app_startup(d: u2.Device, seconds: int = 6, max_relaunches: int = 2) -> None:
    ensure_app_front(d)
    log(f"stabilize app startup for {seconds}s")
    deadline = time.time() + max(1, seconds)
    relaunches = 0
    while time.time() < deadline:
        time.sleep(1.0)
        handle_anr_dialog(d)
        if current_package(d) != PKG:
            relaunches += 1
            if relaunches > max_relaunches:
                raise RuntimeError(
                    f"startup unstable: dropped from foreground too often ({relaunches - 1} relaunches)"
                )
            log(f"startup unstable: app dropped from foreground, relaunching ({relaunches}/{max_relaunches})")
            ensure_app_front(d)


def tap_first(
    d: u2.Device,
    selectors: list,
    *,
    label: str = "tap",
    retries_per_selector: int = 2,
    post_wait: tuple[float, float] = (1.0, 1.6),
    verify: Callable[[], bool] | None = None,
) -> bool:
    for sel in selectors:
        for attempt in range(1, retries_per_selector + 1):
            if not sel.exists:
                break
            try:
                sel.click()
            except Exception:
                continue
            sleep_rand(*post_wait)
            if verify is not None:
                if verify():
                    return True
            else:
                return True
            if attempt < retries_per_selector:
                log(f"{label}: retry tap {attempt + 1}/{retries_per_selector}")
    return False


def tap_point_stable(
    d: u2.Device,
    x: int,
    y: int,
    *,
    label: str,
    verify: Callable[[], bool] | None = None,
    retries: int = 2,
    post_wait: tuple[float, float] = (1.0, 1.8),
) -> bool:
    for attempt in range(1, retries + 1):
        d.click(x, y)
        sleep_rand(*post_wait)
        if verify is None or verify():
            return True
        if attempt < retries:
            log(f"{label}: retry tap {attempt + 1}/{retries}")
    return False


def home_tab_visible(d: u2.Device) -> bool:
    if current_package(d) != PKG:
        return False
    patterns = [
        r"(?i)(trang ch\u1ee7|home)",
        r"(?i)(kh\u00e1m ph\u00e1|discover)",
        r"(?i)(h\u1ed9p th\u01b0|hop thu|inbox)",
        r"(?i)(t\u00f4i|profile|me)",
    ]
    return any(
        d(textMatches=p, packageName=PKG).exists or d(descriptionMatches=p, packageName=PKG).exists for p in patterns
    )


def go_home_tab(d: u2.Device) -> None:
    ensure_app_front(d)
    ensure_tiktok_context(d, "go_home_tab")
    if tap_first(
        d,
        [
            d(textMatches=r"(?i)(trang ch\u1ee7|home)", packageName=PKG),
            d(descriptionMatches=r"(?i)(trang ch\u1ee7|home)", packageName=PKG),
        ],
        label="go_home_tab home-selector",
        verify=lambda: home_tab_visible(d),
    ):
        return
    w, h = d.window_size()
    if not tap_point_stable(
        d,
        int(w * 0.12),
        int(h * 0.965),
        label="go_home_tab bottom-left fallback",
        verify=lambda: home_tab_visible(d),
        retries=2,
    ):
        log("go_home_tab: home-tab text not confirmed after fallback taps; continue with app-front context")


def warmup_before_search(d: u2.Device, swipes: int = 1) -> None:
    if swipes <= 0:
        return
    if current_package(d) != PKG:
        return
    if not home_tab_visible(d):
        return

    w, h = d.window_size()
    log(f"pre-search warmup swipe x{swipes}")
    for _ in range(swipes):
        if current_package(d) != PKG:
            return
        # Small up/down gestures to warm UI without drifting too far from current state.
        d.swipe(int(w * 0.50), int(h * 0.78), int(w * 0.50), int(h * 0.66), 0.16)
        sleep_rand(0.8, 1.3)
        d.swipe(int(w * 0.50), int(h * 0.66), int(w * 0.50), int(h * 0.74), 0.16)
        sleep_rand(0.7, 1.2)


def open_search(d: u2.Device) -> None:
    warmup_done = False
    for nav_attempt in range(1, 4):
        ensure_app_front(d)
        if current_package(d) != PKG:
            log(f"open_search attempt {nav_attempt}/3: not in TikTok yet, relaunching")
            continue

        log("open search tab")
        if find_search_box(d) is not None:
            log("search box already visible")
            return

        if not warmup_done and PRE_SEARCH_WARMUP_SWIPES > 0:
            warmup_before_search(d, swipes=PRE_SEARCH_WARMUP_SWIPES)
            warmup_done = True
            if current_package(d) != PKG:
                log(f"open_search attempt {nav_attempt}/3: context dropped after warmup swipe")
                continue

        # First, try entering Discover tab in bottom navigation.
        discover_ok = tap_first(
            d,
            [
                d(textMatches=r"(?i)(kh\u00e1m ph\u00e1|kham pha|discover)", packageName=PKG),
                d(descriptionMatches=r"(?i)(kh\u00e1m ph\u00e1|kham pha|discover)", packageName=PKG),
            ],
            label="open_search discover-tab",
            post_wait=(1.2, 2.0),
        )
        if discover_ok:
            log("tapped discover tab")
            sleep_rand(1.0, 1.6)
            if current_package(d) != PKG:
                log(f"open_search attempt {nav_attempt}/3: context dropped after discover tap")
                continue

        # Then, explicitly open Search entry point.
        search_ok = tap_first(
            d,
            [
                d(textMatches=r"(?i)(t\u00ecm ki\u1ebfm|tim kiem|search)", packageName=PKG),
                d(descriptionMatches=r"(?i)(t\u00ecm ki\u1ebfm|tim kiem|search)", packageName=PKG),
            ],
            label="open_search search-entry",
            verify=lambda: find_search_box(d) is not None,
            post_wait=(1.2, 2.0),
        )
        if not search_ok:
            if current_package(d) != PKG:
                log(f"open_search attempt {nav_attempt}/3: context dropped before fallback tap")
                continue
            log("search icon not found by selector, fallback tap top-right")
            w, h = d.window_size()
            tap_point_stable(
                d,
                int(w * 0.92),
                int(h * 0.09),
                label="open_search top-right fallback",
                verify=lambda: find_search_box(d) is not None,
                retries=2,
                post_wait=(1.2, 2.0),
            )
        else:
            log("tapped search icon")
        sleep_rand(1.4, 2.2)

        if current_package(d) != PKG:
            log(f"open_search attempt {nav_attempt}/3: context dropped after search-entry tap")
            continue

        if find_search_box(d) is None:
            # Some builds need one more explicit tap on top bar to focus search.
            w, h = d.window_size()
            tap_point_stable(
                d,
                int(w * 0.50),
                int(h * 0.08),
                label="open_search top-bar fallback",
                verify=lambda: find_search_box(d) is not None,
                retries=2,
                post_wait=(0.9, 1.4),
            )
            log("fallback tap top search bar area")
            sleep_rand(1.0, 1.5)
            if current_package(d) != PKG:
                log(f"open_search attempt {nav_attempt}/3: context dropped after top-bar fallback")
                continue

        if find_search_box(d) is not None:
            return

    raise RuntimeError("open_search failed after 3 retries due unstable app context")


def find_search_box(d: u2.Device):
    if current_package(d) != PKG:
        return None
    candidates = [
        d(className="android.widget.EditText", packageName=PKG),
        d(className="android.widget.EditText", focused=True, packageName=PKG),
        d(className="android.widget.AutoCompleteTextView", packageName=PKG),
        d(className="android.widget.AutoCompleteTextView", focused=True, packageName=PKG),
    ]
    for sel in candidates:
        if sel.exists:
            return sel
    return None


def keyword_visible_in_ui(d: u2.Device, keyword: str) -> bool:
    if current_package(d) != PKG:
        return False
    k = normalize_text(keyword)
    if not k:
        return False
    try:
        xml = d.dump_hierarchy(compressed=False, pretty=False)
    except Exception:
        return False
    return k in normalize_text(xml)


def capture_evidence(d: u2.Device, evidence_dir: Path | None, label: str) -> None:
    if evidence_dir is None:
        return
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", label).strip("_")
    png_path = evidence_dir / f"{stamp}_{safe}.png"
    xml_path = evidence_dir / f"{stamp}_{safe}.xml"
    try:
        d.screenshot(str(png_path))
    except Exception:
        pass
    try:
        xml = d.dump_hierarchy(compressed=False, pretty=False)
        xml_path.write_text(xml, encoding="utf-8", errors="ignore")
    except Exception:
        pass


def choose_keyword(force_keyword: str | None) -> str:
    if force_keyword:
        return force_keyword
    return random.choice(KEYWORDS)


def search_keyword(d: u2.Device, keyword: str) -> None:
    for attempt in range(1, 6):
        ensure_app_front(d)
        ensure_tiktok_context(d, f"search_keyword attempt {attempt} begin")
        handle_anr_dialog(d)

        box = find_search_box(d)
        if box is not None and box.exists:
            log(f"search input ready (attempt {attempt}/5)")
            try:
                box.click()
                sleep_rand(0.5, 1.0)
            except Exception:
                pass
            try:
                box.set_text(keyword)
            except Exception:
                # fallback: focus top bar then set_text again
                w, h = d.window_size()
                tap_point_stable(
                    d,
                    int(w * 0.5),
                    int(h * 0.08),
                    label="search_keyword focus top bar",
                    verify=lambda: find_search_box(d) is not None,
                    retries=2,
                    post_wait=(0.7, 1.2),
                )
                box = find_search_box(d)
                if box is None or not box.exists:
                    raise RuntimeError("Search box not available")
                box.set_text(keyword)

            log(f"typed keyword: {keyword}")
            sleep_rand(1.0, 1.5)
            ensure_tiktok_context(d, f"search_keyword attempt {attempt} before enter")
            d.press("enter")
            log("submitted keyword search")
            sleep_rand(1.9, 2.8)
            ensure_tiktok_context(d, f"search_keyword attempt {attempt} after enter")
            if keyword_visible_in_ui(d, keyword):
                log("search verification: keyword visible on UI")
                return

            log("search verification failed, retrying search flow")
            open_search(d)
            continue

        # Retry by reopening search.
        open_search(d)
        log(f"search box retry {attempt}/5")

    raise RuntimeError(f"Search step failed: keyword '{keyword}' not confirmed on UI")


def scroll_search_result_two_lines(d: u2.Device) -> None:
    log("scroll search results 2 lines")
    w, h = d.window_size()
    for _ in range(2):
        d.swipe(int(w * 0.50), int(h * 0.80), int(w * 0.50), int(h * 0.25), 0.24)
        sleep_rand(1.1, 1.8)


def dismiss_keyboard_focus(d: u2.Device) -> None:
    # Avoid using BACK here because it can leave search results unexpectedly.
    # A light tap under the search bar is safer to defocus input.
    w, h = d.window_size()
    tap_point_stable(
        d,
        int(w * 0.50),
        int(h * 0.22),
        label="dismiss_keyboard_focus",
        retries=2,
        post_wait=(0.5, 0.9),
    )


def parse_bounds(bounds: str) -> tuple[int, int, int, int] | None:
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def count_right_action_nodes(d: u2.Device) -> int:
    # Video player usually has 3+ clickable actions on right side
    # (like/comment/share/profile). Use this as a robust signal.
    xml = d.dump_hierarchy(compressed=False, pretty=False)
    matches = re.finditer(
        r'class="([^"]+)"[^>]*package="com\.zhiliaoapp\.musically\.go"[^>]*clickable="true"[^>]*bounds="(\[[^"]+\])"',
        xml,
    )
    count = 0
    for m in matches:
        b = parse_bounds(m.group(2))
        if not b:
            continue
        x1, y1, x2, y2 = b
        if x1 >= 450 and y1 >= 180 and (y2 - y1) >= 45:
            count += 1
    return count


def is_video_open(d: u2.Device) -> bool:
    cur = d.app_current()
    activity = cur.get("activity", "")
    if activity.endswith("DetailActivity"):
        return True

    # Spark web page / search pages are not video players.
    if "SparkActivity" in activity:
        return False

    # If search box still exists, we are still on search-related pages.
    if find_search_box(d) is not None:
        return False

    if home_tab_visible(d):
        return False

    return count_right_action_nodes(d) >= 3


def get_result_tile_points(d: u2.Device) -> list[tuple[int, int]]:
    xml = d.dump_hierarchy(compressed=False, pretty=False)
    nodes = re.finditer(
        r'class="android\.view\.ViewGroup"[^>]*package="com\.zhiliaoapp\.musically\.go"[^>]*clickable="true"[^>]*bounds="(\[[^"]+\])"',
        xml,
    )
    points: list[tuple[int, int]] = []
    for m in nodes:
        b = parse_bounds(m.group(1))
        if not b:
            continue
        x1, y1, x2, y2 = b
        w = x2 - x1
        h = y2 - y1
        # Skip top chips and tiny elements; keep big result tiles only.
        if y1 < 220 or w < 180 or h < 180:
            continue
        points.append(((x1 + x2) // 2, (y1 + y2) // 2))

    # Stable order: upper row first, then lower rows.
    points = sorted(points, key=lambda p: (p[1], p[0]))
    dedup: list[tuple[int, int]] = []
    for p in points:
        if p not in dedup:
            dedup.append(p)
    return dedup


def recover_back_to_search_results(d: u2.Device) -> None:
    for _ in range(3):
        if find_search_box(d) is not None:
            return
        d.press("back")
        sleep_rand(0.7, 1.2)


def open_first_visible_video(d: u2.Device) -> None:
    ensure_app_front(d)
    dismiss_keyboard_focus(d)
    log("open first visible video from results")
    points = get_result_tile_points(d)
    if not points:
        w, h = d.window_size()
        # Conservative fallback points in result area.
        points = [
            (int(w * 0.22), int(h * 0.34)),
            (int(w * 0.50), int(h * 0.34)),
            (int(w * 0.22), int(h * 0.48)),
            (int(w * 0.50), int(h * 0.48)),
        ]

    for idx, (x, y) in enumerate(points, start=1):
        log(f"try open video candidate {idx} at ({x},{y})")
        opened = tap_point_stable(
            d,
            x,
            y,
            label=f"open_video candidate {idx}",
            verify=lambda: is_video_open(d),
            retries=2,
            post_wait=(1.2, 2.0),
        )
        if opened:
            cur = d.app_current()
            log(f"video opened: activity={cur.get('activity', '')}")
            return
        recover_back_to_search_results(d)

    cur = d.app_current()
    raise RuntimeError(f"Cannot open first visible video. activity={cur.get('activity', '')}")


def parse_mmss_to_sec(text: str) -> int | None:
    try:
        mm, ss = text.split(":")
        return int(mm) * 60 + int(ss)
    except Exception:
        return None


def estimate_current_video_seconds(d: u2.Device, fallback_sec: int) -> int:
    # Best effort parse from accessibility dump:
    # formats like "00:12 / 00:45"
    xml = d.dump_hierarchy(compressed=False, pretty=False)
    m = re.search(r"(\d{1,2}:\d{2})\s*/\s*(\d{1,2}:\d{2})", xml)
    if m:
        total = parse_mmss_to_sec(m.group(2))
        if total and total > 0:
            return max(8, min(total + 2, 180))
    return fallback_sec


def watch_current_video_to_end(d: u2.Device, fallback_sec: int) -> None:
    sec = estimate_current_video_seconds(d, fallback_sec=fallback_sec)
    log(f"wait current video ~{sec}s")
    wait_with_healthcheck(d, sec)


def swipe_to_next_video(d: u2.Device) -> None:
    w, h = d.window_size()
    d.swipe(int(w * 0.50), int(h * 0.80), int(w * 0.50), int(h * 0.24), 0.22)
    sleep_rand(1.1, 1.7)


def watch_next_three_videos(d: u2.Device, min_sec: int = 5, max_sec: int = 10) -> None:
    for idx in range(1, 4):
        sec = random.randint(min_sec, max_sec)
        log(f"watch video {idx} for {sec}s")
        wait_with_healthcheck(d, sec)
        swipe_to_next_video(d)


def wait_with_healthcheck(d: u2.Device, total_sec: int, poll_sec: float = 1.0) -> None:
    deadline = time.time() + max(0, total_sec)
    while True:
        remain = deadline - time.time()
        if remain <= 0:
            return
        time.sleep(min(poll_sec, remain))

        handle_anr_dialog(d)
        pkg = d.app_current().get("package", "")
        if pkg != PKG:
            log(f"app left foreground while waiting (pkg={pkg or 'unknown'}), recovering")
            ensure_app_front(d)


def recover_to_known_state(d: u2.Device) -> None:
    log("recover: reset app state to TikTok home")
    try:
        d.app_stop(PKG)
    except Exception:
        run_cmd(["adb", "shell", "am", "force-stop", PKG], check=False, timeout=10)
    sleep_rand(0.8, 1.4)
    ensure_app_front(d)
    stabilize_app_startup(d, seconds=4)
    go_home_tab(d)


def stop_tiktok_app(serial: str, d: u2.Device | None = None) -> None:
    log("cleanup: stopping TikTok app")
    if d is not None:
        try:
            d.app_stop(PKG)
        except Exception:
            pass
    run_cmd(["adb", "-s", serial, "shell", "am", "force-stop", PKG], check=False, timeout=10)


def back_to_home_tab(d: u2.Device) -> None:
    ensure_app_front(d)
    for _ in range(6):
        if home_tab_visible(d):
            break
        d.press("back")
        sleep_rand(0.7, 1.2)
    go_home_tab(d)


def run_flow(d: u2.Device, keyword: str, current_video_fallback: int, evidence_dir: Path | None) -> None:
    stabilize_app_startup(d, seconds=5)
    log("step 1: go home")
    go_home_tab(d)
    capture_evidence(d, evidence_dir, "step1_home")
    log("step 2: open search")
    open_search(d)
    capture_evidence(d, evidence_dir, "step2_open_search")
    log("step 3: search keyword")
    search_keyword(d, keyword)
    capture_evidence(d, evidence_dir, "step3_after_search")
    log("step 4: scroll results")
    scroll_search_result_two_lines(d)
    capture_evidence(d, evidence_dir, "step4_scrolled_results")
    log("step 5: open first video")
    open_first_visible_video(d)
    capture_evidence(d, evidence_dir, "step5_open_video")
    log("step 6: watch current video to end")
    watch_current_video_to_end(d, fallback_sec=current_video_fallback)
    log("step 7: watch next 3 videos")
    watch_next_three_videos(d, min_sec=5, max_sec=10)
    log("step 8: return to home")
    back_to_home_tab(d)
    capture_evidence(d, evidence_dir, "step8_back_home")


def run_flow_with_retry(
    d: u2.Device,
    keyword: str,
    current_video_fallback: int,
    evidence_dir: Path | None,
    max_attempts: int = 3,
) -> None:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        log(f"flow attempt {attempt}/{max_attempts}")
        try:
            run_flow(
                d,
                keyword=keyword,
                current_video_fallback=current_video_fallback,
                evidence_dir=evidence_dir,
            )
            return
        except Exception as exc:
            last_exc = exc
            log(f"flow attempt {attempt} failed: {exc}")
            capture_evidence(d, evidence_dir, f"flow_attempt_{attempt}_failed")
            if attempt >= max_attempts:
                break
            recover_to_known_state(d)
            sleep_rand(1.0, 1.8)

    raise FlowExecutionError(f"Flow failed after {max_attempts} attempts: {last_exc}")


def main() -> int:
    global DELAY_MULTIPLIER, PRE_SEARCH_WARMUP_SWIPES

    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default=DEFAULT_SERIAL, help="ADB serial. Default: 127.0.0.1:16448")
    parser.add_argument("--keyword", default=None, help="Fixed keyword. If omitted, random from built-in list.")
    parser.add_argument(
        "--current-video-fallback-secs",
        type=int,
        default=45,
        help="Fallback seconds to wait current video if duration is not detectable.",
    )
    parser.add_argument(
        "--evidence-dir",
        default=r"C:\Users\Admin\Documents\New project\tiktok_evidence",
        help="Directory to save per-step screenshots/xml evidence.",
    )
    parser.add_argument(
        "--delay-multiplier",
        type=float,
        default=DEFAULT_DELAY_MULTIPLIER,
        help="Scale interaction timing for slower/more stable behavior. Default: 1.2",
    )
    parser.add_argument(
        "--pre-search-warmup-swipes",
        type=int,
        default=PRE_SEARCH_WARMUP_SWIPES,
        help="Light warmup swipes before opening Search (0-2 recommended). Default: 1",
    )
    args = parser.parse_args()

    if args.current_video_fallback_secs <= 0:
        raise RuntimeError("--current-video-fallback-secs must be > 0")
    if args.delay_multiplier <= 0:
        raise RuntimeError("--delay-multiplier must be > 0")
    if args.pre_search_warmup_swipes < 0 or args.pre_search_warmup_swipes > 3:
        raise RuntimeError("--pre-search-warmup-swipes must be between 0 and 3")

    DELAY_MULTIPLIER = args.delay_multiplier
    PRE_SEARCH_WARMUP_SWIPES = args.pre_search_warmup_swipes

    preflight_check(args.serial)
    ensure_adb_ready(args.serial, timeout_sec=120)
    import uiautomator2 as u2

    d = u2.connect(args.serial)
    d.implicitly_wait(5)
    d.screen_on()

    keyword = choose_keyword(args.keyword)
    log(f"serial: {args.serial}")
    log(f"keyword: {keyword}")
    log(f"delay multiplier: {DELAY_MULTIPLIER:.2f}")
    log(f"pre-search warmup swipes: {PRE_SEARCH_WARMUP_SWIPES}")
    evidence_dir = Path(args.evidence_dir) if args.evidence_dir else None

    try:
        run_flow_with_retry(
            d,
            keyword=keyword,
            current_video_fallback=args.current_video_fallback_secs,
            evidence_dir=evidence_dir,
        )
        log("flow completed")
        return EXIT_OK
    finally:
        stop_tiktok_app(args.serial, d)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DevicePrepError as exc:
        log(f"DEVICE_PREP_FAILED: {exc}")
        sys.exit(EXIT_DEVICE_ERROR)
    except FlowExecutionError as exc:
        log(f"FLOW_FAILED: {exc}")
        sys.exit(EXIT_FLOW_ERROR)
    except Exception as exc:
        log(f"FAILED: {exc}")
        sys.exit(EXIT_GENERIC_ERROR)
