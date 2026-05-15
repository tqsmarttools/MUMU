import importlib.util
import json
import time
from datetime import datetime
from pathlib import Path

SCRIPT_PATH = Path(r"D:\MUMU\scripts\tt_g2_1_open_tiktok_plus.py")
LOG_DIR = Path(r"D:\MUMU\scripts\logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("tt_g2_1", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

serial = "127.0.0.1:16448"
loops = 10

run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out_json = LOG_DIR / f"tt_g2_1_plus_stress_{run_ts}.json"

results = []
start_all = time.time()

mod.log(f"PLUS STRESS TEST start: loops={loops} serial={serial}")
d = mod.connect_device_with_retry(serial, max_retries=4)

for i in range(1, loops + 1):
    t0 = time.time()
    row = {
        "iteration": i,
        "status": "FAIL",
        "error": "",
        "duration_sec": 0.0,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    mod.log(f"[loop {i}/{loops}] begin")
    try:
        mod.ensure_adb_ready(serial, timeout_sec=60)
        mod.ensure_tiktok_home(d)
        mod.tap_plus_random(d, max_attempts=4)
        if not mod.is_creation_screen(d):
            cur = d.app_current()
            raise RuntimeError(
                "'+' tap did not land on creation screen: "
                f"pkg={cur.get('package','')} act={cur.get('activity','')}"
            )
        row["status"] = "PASS"
        mod.log(f"[loop {i}/{loops}] PASS: creation screen opened")
    except Exception as exc:
        row["error"] = str(exc)
        mod.log(f"[loop {i}/{loops}] FAIL: {exc}")
        if "offline" in str(exc).lower():
            try:
                d = mod.connect_device_with_retry(serial, max_retries=3)
            except Exception as reconnect_exc:
                mod.log(f"[loop {i}/{loops}] reconnect failed: {reconnect_exc}")
    finally:
        try:
            d.app_stop(mod.PKG)
        except Exception:
            pass
        try:
            d.press("home")
        except Exception:
            pass
        mod.human_sleep(0.8, 1.3)
        row["duration_sec"] = round(time.time() - t0, 2)
        results.append(row)

summary = {
    "serial": serial,
    "loops": loops,
    "passed": sum(1 for r in results if r["status"] == "PASS"),
    "failed": sum(1 for r in results if r["status"] != "PASS"),
    "total_duration_sec": round(time.time() - start_all, 2),
    "results": results,
}

out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

mod.log("PLUS STRESS TEST completed")
mod.log(f"summary: pass={summary['passed']} fail={summary['failed']} total={summary['loops']} total_sec={summary['total_duration_sec']}")
mod.log(f"result file: {out_json}")

print(json.dumps(summary, ensure_ascii=False))
