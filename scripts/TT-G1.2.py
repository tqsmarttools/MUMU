#!/usr/bin/env python3
"""
TT-G1.2 - TikTok standard flow (stable, step-by-step)

Design goals:
1) Always enforce SocksDroid fake IP gate before opening TikTok.
2) Remove random tap points for critical navigation.
3) Verify screen state after every step before moving forward.
4) Support stage-by-stage runs for safer debugging.
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


PKG = "com.zhiliaoapp.musically"
SOCKS_PKG = "net.typeblog.socks"
SOCKS_SWITCH_RID = "net.typeblog.socks:id/switch_action_button"
GOOGLE_GMS_PKG = "com.google.android.gms"
DEFAULT_SERIAL = "127.0.0.1:16448"
DEFAULT_DELAY_MULTIPLIER = 1.3
SOCKS_BASE_WIDTH = 540.0
SOCKS_BASE_HEIGHT = 960.0

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

DELAY_MULTIPLIER = DEFAULT_DELAY_MULTIPLIER


class DevicePrepError(RuntimeError):
    """Raised when adb/device preparation cannot be completed."""


class FlowExecutionError(RuntimeError):
    """Raised when UI flow cannot be completed safely."""


def log(msg: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def sleep_rand(lo: float = 0.8, hi: float = 1.4) -> None:
    lo_s = max(0.05, lo * DELAY_MULTIPLIER)
    hi_s = max(lo_s, hi * DELAY_MULTIPLIER)
    time.sleep(random.uniform(lo_s, hi_s))


def run_cmd(cmd: list[str], check: bool = False, timeout: int = 25) -> subprocess.CompletedProcess[str]:
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


def ensure_adb_ready(serial: str, timeout_sec: int = 120) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        cp = run_cmd(["adb", "devices"], check=False, timeout=15)
        state = None
        for line in cp.stdout.splitlines():
            if line.startswith(serial + "\t"):
                state = line.split("\t", 1)[1].strip()
                break
        if state == "device":
            return
        if state == "offline":
            run_cmd(["adb", "disconnect", serial], check=False, timeout=10)
        run_cmd(["adb", "connect", serial], check=False, timeout=10)
        time.sleep(2.0)
    raise DevicePrepError(f"ADB not ready for {serial}")


def shell_output(d: u2.Device, cmd: str) -> str:
    try:
        result = d.shell(cmd)
    except Exception:
        return ""

    if isinstance(result, tuple):
        return str(result[0] or "")
    if hasattr(result, "output"):
        return str(getattr(result, "output") or "")
    return str(result or "")


def current_package(d: u2.Device) -> str:
    try:
        return d.app_current().get("package", "")
    except Exception:
        return ""


def wait_until(fn: Callable[[], bool], timeout_sec: float, poll_sec: float = 0.4) -> bool:
    deadline = time.time() + max(0.1, timeout_sec)
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(poll_sec)
    return False


def handle_anr_dialog(d: u2.Device) -> bool:
    anr_exists = (
        d(resourceId="android:id/alertTitle").exists
        or d(resourceId="android:id/aerr_wait").exists
        or d(resourceId="android:id/aerr_close").exists
        or d(textMatches=r"(?i)(khÃ´ng pháº£n há»“i|not responding|isn't responding)").exists
    )
    if not anr_exists:
        return False

    log("ANR popup detected, trying recover")
    for sel in [
        d(resourceId="android:id/aerr_close"),
        d(textMatches=r"(?i)(Ä‘Ã³ng á»©ng dá»¥ng|close app|force close)"),
    ]:
        if sel.exists:
            try:
                sel.click()
                sleep_rand(0.8, 1.2)
                return True
            except Exception:
                continue

    for sel in [
        d(resourceId="android:id/aerr_wait"),
        d(textMatches=r"(?i)(Ä‘á»£i|wait)"),
    ]:
        if sel.exists:
            try:
                sel.click()
                sleep_rand(0.8, 1.2)
                return True
            except Exception:
                continue
    return False


def dismiss_google_signin_sheet(d: u2.Device) -> bool:
    if current_package(d) != GOOGLE_GMS_PKG:
        return False

    log("Google Sign-in sheet detected, dismissing")
    for sel in [
        d(resourceId="com.google.android.gms:id/cancel"),
        d(textMatches=r"(?i)^(há»§y|huá»·|cancel|close)$"),
        d(descriptionMatches=r"(?i)(há»§y|huá»·|cancel|close)"),
    ]:
        if sel.exists:
            try:
                sel.click()
                sleep_rand(0.6, 1.0)
                return True
            except Exception:
                continue

    w, h = d.window_size()
    d.click(int(w * 0.91), int(h * 0.24))
    sleep_rand(0.6, 1.0)
    return True


def is_fake_ip_vpn_active(d: u2.Device) -> bool:
    connectivity = shell_output(d, "dumpsys connectivity")
    if not connectivity:
        return False
    if "VPN CONNECTED" not in connectivity.upper():
        return False
    return bool(re.search(r"InterfaceName:\s*tun0", connectivity, flags=re.IGNORECASE))


def accept_vpn_dialog_if_present(d: u2.Device) -> bool:
    if current_package(d) != "com.android.vpndialogs":
        return False

    log("VPN permission dialog detected, accepting")
    for sel in [
        d(resourceId="android:id/button1"),
        d(textMatches=r"(?i)^(allow|ok|cho phÃ©p|Ä‘á»“ng Ã½|dong y)$"),
        d(descriptionMatches=r"(?i)^(allow|ok|cho phÃ©p|Ä‘á»“ng Ã½|dong y)$"),
    ]:
        if sel.exists:
            try:
                sel.click()
                sleep_rand(0.6, 1.0)
                return True
            except Exception:
                continue

    w, h = d.window_size()
    d.click(int(w * 0.84), int(h * 0.91))
    sleep_rand(0.6, 1.0)
    return True


def tap_point(d: u2.Device, x_ratio: float, y_ratio: float, label: str) -> None:
    w, h = d.window_size()
    x = int(max(1, min(w - 1, round(w * x_ratio))))
    y = int(max(1, min(h - 1, round(h * y_ratio))))
    log(f"tap {label} at ({x},{y})")
    d.click(x, y)


def open_socksdroid(d: u2.Device) -> None:
    try:
        d.app_start(SOCKS_PKG, use_monkey=False)
    except Exception:
        pass
    sleep_rand(0.8, 1.3)
    if current_package(d) == SOCKS_PKG:
        return

    try:
        d.shell(f"monkey -p {SOCKS_PKG} -c android.intent.category.LAUNCHER 1")
    except Exception:
        pass
    sleep_rand(0.8, 1.3)


def ensure_socksdroid_fake_ip_ready(d: u2.Device, max_attempts: int = 3) -> None:
    if is_fake_ip_vpn_active(d):
        log("SocksDroid gate: VPN fake IP already active")
        return

    for attempt in range(1, max_attempts + 1):
        log(f"SocksDroid gate attempt {attempt}/{max_attempts}")
        open_socksdroid(d)

        switch_sel = d(resourceId=SOCKS_SWITCH_RID)
        if switch_sel.exists:
            checked = False
            try:
                checked = bool((switch_sel.info or {}).get("checked", False))
            except Exception:
                checked = False
            log(f"SocksDroid switch checked={checked}")
            if not checked:
                try:
                    switch_sel.click()
                except Exception:
                    pass
                sleep_rand(0.8, 1.2)
        else:
            w, h = d.window_size()
            x = int(round((445.0 / SOCKS_BASE_WIDTH) * w))
            y = int(round((78.0 / SOCKS_BASE_HEIGHT) * h))
            log(f"SocksDroid switch fallback tap at ({x},{y})")
            d.click(x, y)
            sleep_rand(0.8, 1.2)

        accept_vpn_dialog_if_present(d)
        if wait_until(lambda: is_fake_ip_vpn_active(d), timeout_sec=35, poll_sec=0.8):
            log("SocksDroid gate: VPN fake IP active")
            return
        log("SocksDroid gate: VPN still inactive, retrying")

    raise DevicePrepError("SocksDroid fake IP is not active. Stop by safety rule.")


def ensure_app_front(d: u2.Device, package_name: str, retries: int = 3) -> None:
    for attempt in range(1, retries + 1):
        handle_anr_dialog(d)
        dismiss_google_signin_sheet(d)

        if current_package(d) == package_name:
            return

        log(f"bring app front {package_name} attempt {attempt}/{retries}")
        if package_name == PKG:
            # Critical rule from user: never open TikTok before fake IP is active.
            ensure_socksdroid_fake_ip_ready(d)
        try:
            d.app_start(package_name, use_monkey=False)
        except Exception:
            pass
        sleep_rand(1.0, 1.6)

        if wait_until(lambda: current_package(d) == package_name, timeout_sec=12, poll_sec=0.6):
            return

    cur = current_package(d)
    raise FlowExecutionError(f"Cannot bring app to front. expected={package_name}, current={cur or 'unknown'}")


def home_nav_visible(d: u2.Device) -> bool:
    if current_package(d) != PKG:
        return False
    patterns = [
        r"(?i)(trang chá»§|home)",
        r"(?i)(khÃ¡m phÃ¡|discover)",
        r"(?i)(há»™p thÆ°|inbox)",
        r"(?i)(há»“ sÆ¡|profile|me|tÃ´i)",
    ]
    for p in patterns:
        if d(textMatches=p, packageName=PKG).exists or d(descriptionMatches=p, packageName=PKG).exists:
            return True
    return False


def is_search_screen(d: u2.Device) -> bool:
    if current_package(d) != PKG:
        return False
    selectors = [
        d(className="android.widget.EditText", packageName=PKG),
        d(className="android.widget.EditText", focused=True, packageName=PKG),
        d(className="android.widget.AutoCompleteTextView", packageName=PKG),
    ]
    return any(sel.exists for sel in selectors)


def dismiss_feed_coachmark(d: u2.Device) -> bool:
    if current_package(d) != PKG:
        return False
    patterns = [
        r"(?i).*vuá»‘t lÃªn.*",
        r"(?i).*swipe up.*",
        r"(?i).*Ä‘á»ƒ xem thÃªm.*",
    ]
    if not any(d(textMatches=p).exists for p in patterns):
        return False

    log("feed coachmark detected, dismiss by swipe")
    w, h = d.window_size()
    d.swipe(int(w * 0.50), int(h * 0.80), int(w * 0.50), int(h * 0.28), 0.24)
    sleep_rand(1.0, 1.4)
    return True


def open_tiktok_home(d: u2.Device) -> None:
    ensure_app_front(d, PKG)
    sleep_rand(1.8, 2.6)
    if current_package(d) != PKG:
        raise FlowExecutionError("TikTok dropped from foreground right after launch")

    # Tap Home tab anchor once to stabilize on main feed.
    tap_point(d, 0.10, 0.965, "home-tab anchor")
    sleep_rand(1.0, 1.6)
    if current_package(d) != PKG:
        raise FlowExecutionError("TikTok dropped from foreground after home-tab anchor")


def swipe_home_feed(d: u2.Device, min_swipes: int = 2, max_swipes: int = 3) -> None:
    if min_swipes <= 0 or max_swipes < min_swipes:
        raise FlowExecutionError("Invalid swipe range")

    ensure_app_front(d, PKG)
    swipes = random.randint(min_swipes, max_swipes)
    w, h = d.window_size()
    log(f"home feed swipe count: {swipes}")
    for idx in range(1, swipes + 1):
        if current_package(d) != PKG:
            raise FlowExecutionError(f"Lost TikTok context before swipe {idx}")
        log(f"swipe home feed {idx}/{swipes}")
        d.swipe(int(w * 0.50), int(h * 0.80), int(w * 0.50), int(h * 0.30), 0.25)
        sleep_rand(1.2, 1.9)


def back_to_home_tab(d: u2.Device) -> None:
    ensure_app_front(d, PKG)
    for _ in range(4):
        if current_package(d) != PKG:
            raise FlowExecutionError("Lost TikTok context while returning home")
        if home_nav_visible(d) and not is_search_screen(d):
            tap_point(d, 0.10, 0.965, "home-tab confirm")
            sleep_rand(0.9, 1.3)
            if current_package(d) != PKG:
                raise FlowExecutionError("Lost TikTok context after home-tab confirm")
            return
        d.press("back")
        sleep_rand(0.8, 1.2)

    tap_point(d, 0.10, 0.965, "home-tab fallback")
    sleep_rand(1.0, 1.5)
    if current_package(d) != PKG:
        raise FlowExecutionError("Cannot return home: TikTok left foreground")


def open_search_screen(d: u2.Device) -> None:
    if is_search_screen(d):
        log("search screen already visible")
        return

    for attempt in range(1, 4):
        log(f"open_search_screen attempt {attempt}/3")
        ensure_app_front(d, PKG)
        if current_package(d) != PKG:
            continue

        dismiss_feed_coachmark(d)

        discover_hit = False
        for sel in [
            d(textMatches=r"(?i)(kham pha|discover)", packageName=PKG),
            d(descriptionMatches=r"(?i)(kham pha|discover)", packageName=PKG),
        ]:
            if sel.exists:
                try:
                    sel.click()
                    discover_hit = True
                    log("open_search_screen: tapped discover selector")
                    sleep_rand(1.0, 1.6)
                    break
                except Exception:
                    continue

        if not discover_hit:
            tap_point(d, 0.30, 0.965, "discover-tab fallback")
            sleep_rand(0.9, 1.4)

        if current_package(d) != PKG:
            log(f"open_search_screen attempt {attempt}: lost context after discover step")
            continue

        search_hit = False
        for sel in [
            d(textMatches=r"(?i)(tim kiem|search)", packageName=PKG),
            d(descriptionMatches=r"(?i)(tim kiem|search)", packageName=PKG),
        ]:
            if sel.exists:
                try:
                    sel.click()
                    search_hit = True
                    log("open_search_screen: tapped search selector")
                    sleep_rand(1.0, 1.6)
                    break
                except Exception:
                    continue

        if not search_hit:
            tap_point(d, 0.92, 0.125, "search-icon fallback 1")
            sleep_rand(1.0, 1.6)

        if not is_search_screen(d):
            tap_point(d, 0.92, 0.105, "search-icon fallback 2")
            sleep_rand(0.9, 1.4)

        if not is_search_screen(d):
            tap_point(d, 0.50, 0.115, "search-bar fallback")
            sleep_rand(0.9, 1.4)

        if current_package(d) != PKG:
            log(f"open_search_screen attempt {attempt}: lost TikTok context, retry")
            continue
        if is_search_screen(d):
            return

    raise FlowExecutionError("Cannot open search screen after 3 attempts")


def get_search_box(d: u2.Device):
    if current_package(d) != PKG:
        return None
    for sel in [
        d(className="android.widget.EditText", packageName=PKG),
        d(className="android.widget.EditText", focused=True, packageName=PKG),
        d(className="android.widget.AutoCompleteTextView", packageName=PKG),
        d(className="android.widget.AutoCompleteTextView", focused=True, packageName=PKG),
    ]:
        if sel.exists:
            return sel
    return None


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def keyword_visible_in_ui(d: u2.Device, keyword: str) -> bool:
    if current_package(d) != PKG:
        return False
    try:
        xml = d.dump_hierarchy(compressed=True, pretty=False)
    except Exception:
        return False
    return normalize_text(keyword) in normalize_text(xml)


def choose_keyword(fixed_keyword: str | None) -> str:
    if fixed_keyword:
        return fixed_keyword
    return random.choice(KEYWORDS)


def search_keyword(d: u2.Device, keyword: str) -> None:
    open_search_screen(d)
    ensure_app_front(d, PKG)

    box = get_search_box(d)
    if box is None:
        raise FlowExecutionError("Search box not found")
    try:
        box.click()
    except Exception:
        pass
    sleep_rand(0.5, 0.9)
    box = get_search_box(d)
    if box is None:
        raise FlowExecutionError("Search box lost before typing")

    box.set_text(keyword)
    sleep_rand(0.9, 1.3)
    if current_package(d) != PKG:
        raise FlowExecutionError("Lost TikTok context after typing keyword")

    log(f"submit keyword: {keyword}")
    d.press("enter")
    sleep_rand(1.8, 2.5)

    if current_package(d) != PKG:
        raise FlowExecutionError("Lost TikTok context after pressing Enter")
    if not keyword_visible_in_ui(d, keyword):
        raise FlowExecutionError(f"Search results not confirmed for keyword '{keyword}'")


def tap_result_area_first_tile(d: u2.Device) -> None:
    ensure_app_front(d, PKG)
    # Fixed safe point inside first tile area (left column, first row).
    tap_point(d, 0.22, 0.34, "first-result-tile")
    sleep_rand(1.6, 2.2)


def is_video_activity(d: u2.Device) -> bool:
    if current_package(d) != PKG:
        return False
    try:
        activity = d.app_current().get("activity", "")
    except Exception:
        return False
    return "DetailActivity" in activity


def open_first_video(d: u2.Device) -> None:
    tap_result_area_first_tile(d)
    if current_package(d) != PKG:
        raise FlowExecutionError("Lost TikTok context when opening first video")
    if not is_video_activity(d):
        raise FlowExecutionError("First video not opened (DetailActivity not detected)")


def wait_with_healthcheck(d: u2.Device, total_sec: int) -> None:
    deadline = time.time() + max(0, total_sec)
    while True:
        remain = deadline - time.time()
        if remain <= 0:
            return
        time.sleep(min(1.0, remain))
        handle_anr_dialog(d)
        if current_package(d) != PKG:
            raise FlowExecutionError("TikTok left foreground during watch interval")


def watch_flow(d: u2.Device, current_video_fallback: int = 45) -> None:
    log(f"watch current video ~{current_video_fallback}s")
    wait_with_healthcheck(d, current_video_fallback)
    w, h = d.window_size()
    for idx in range(1, 4):
        sec = random.randint(5, 10)
        log(f"watch next video {idx} for {sec}s")
        wait_with_healthcheck(d, sec)
        d.swipe(int(w * 0.50), int(h * 0.80), int(w * 0.50), int(h * 0.24), 0.22)
        sleep_rand(1.0, 1.5)
        if current_package(d) != PKG:
            raise FlowExecutionError("Lost TikTok context after swipe next video")


def stop_tiktok_app(serial: str, d: u2.Device | None = None) -> None:
    log("cleanup: stopping TikTok app")
    if d is not None:
        try:
            d.app_stop(PKG)
        except Exception:
            pass
    run_cmd(["adb", "-s", serial, "shell", "am", "force-stop", PKG], check=False, timeout=10)


def run_stage(
    d: u2.Device,
    stage: str,
    keyword: str,
    current_video_fallback: int,
) -> None:
    log(f"run stage: {stage}")
    if stage == "gate":
        ensure_socksdroid_fake_ip_ready(d)
        return
    if stage == "open":
        ensure_socksdroid_fake_ip_ready(d)
        open_tiktok_home(d)
        return
    if stage == "search":
        ensure_socksdroid_fake_ip_ready(d)
        open_tiktok_home(d)
        open_search_screen(d)
        return
    if stage == "keyword":
        ensure_socksdroid_fake_ip_ready(d)
        open_tiktok_home(d)
        search_keyword(d, keyword)
        return
    if stage == "video":
        ensure_socksdroid_fake_ip_ready(d)
        open_tiktok_home(d)
        search_keyword(d, keyword)
        open_first_video(d)
        return
    if stage == "full":
        ensure_socksdroid_fake_ip_ready(d)
        open_tiktok_home(d)
        search_keyword(d, keyword)
        open_first_video(d)
        watch_flow(d, current_video_fallback=current_video_fallback)
        return
    if stage == "b1b4":
        ensure_socksdroid_fake_ip_ready(d)
        open_tiktok_home(d)
        swipe_home_feed(d, min_swipes=2, max_swipes=3)
        search_keyword(d, keyword)
        back_to_home_tab(d)
        return
    raise FlowExecutionError(f"Unknown stage: {stage}")


def main() -> int:
    global DELAY_MULTIPLIER

    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default=DEFAULT_SERIAL, help="ADB serial. Default: 127.0.0.1:16448")
    parser.add_argument("--keyword", default=None, help="Fixed keyword. If omitted, random from built-in list.")
    parser.add_argument(
        "--stage",
        default="full",
        choices=["gate", "open", "search", "keyword", "video", "full", "b1b4"],
        help="Run step-by-step stage for stable testing. Default: full",
    )
    parser.add_argument(
        "--current-video-fallback-secs",
        type=int,
        default=45,
        help="Seconds for current video watch in full stage. Default: 45",
    )
    parser.add_argument(
        "--delay-multiplier",
        type=float,
        default=DEFAULT_DELAY_MULTIPLIER,
        help="Scale delays for slower, human-like behavior. Default: 1.3",
    )
    args = parser.parse_args()

    if args.current_video_fallback_secs <= 0:
        raise RuntimeError("--current-video-fallback-secs must be > 0")
    if args.delay_multiplier <= 0:
        raise RuntimeError("--delay-multiplier must be > 0")

    DELAY_MULTIPLIER = args.delay_multiplier
    keyword = choose_keyword(args.keyword)

    preflight_check(args.serial)
    ensure_adb_ready(args.serial, timeout_sec=120)
    import uiautomator2 as u2

    d = u2.connect(args.serial)
    d.implicitly_wait(0.8)
    d.screen_on()

    log(f"serial: {args.serial}")
    log(f"stage: {args.stage}")
    log(f"keyword: {keyword}")
    log(f"delay multiplier: {DELAY_MULTIPLIER:.2f}")

    try:
        run_stage(
            d,
            stage=args.stage,
            keyword=keyword,
            current_video_fallback=args.current_video_fallback_secs,
        )
        log("stage completed")
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

