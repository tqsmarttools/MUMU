#!/usr/bin/env python3
"""
Caption data manager for TikTok MuMu automation.

What this tool does:
1) Keep editable source data in CSV (easy for Excel).
2) Build fast JSON bank used by runtime scripts.
3) Pick random caption by product code (from video filename or explicit code),
   with anti-repeat history per product.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path(r"D:\MUMU\scripts")
DEFAULT_CSV = DEFAULT_ROOT / "data" / "caption_master.csv"
DEFAULT_JSON = DEFAULT_ROOT / "data" / "caption_bank.json"
DEFAULT_HISTORY = DEFAULT_ROOT / "state" / "caption_history.json"
DEFAULT_MAX_CHARS = 1600

CSV_FIELDS = ["product_code", "product_name", "caption", "hashtags", "weight", "active"]


def configure_stdio_utf8() -> None:
    # Prevent Windows default cp1252 console from crashing on Vietnamese text.
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_code(raw: str) -> str:
    text = (raw or "").strip().upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text).strip("_")
    return text or "DEFAULT"


def parse_bool(raw: str, default: bool = True) -> bool:
    text = (raw or "").strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def parse_weight(raw: str, default: int = 1) -> int:
    text = (raw or "").strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError:
        return default
    if value < 1:
        return 1
    if value > 100:
        return 100
    return value


def parse_hashtags(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []

    seen: set[str] = set()
    output: list[str] = []
    for part in re.split(r"[|,;]", text):
        tag = re.sub(r"\s+", "", part.strip())
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = "#" + tag.lstrip("#")
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(tag)
    return output


def stable_caption_id(code: str, caption: str, hashtags: list[str]) -> str:
    payload = f"{code}|{caption}|{'|'.join(hashtags)}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return digest[:16]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def init_csv(csv_path: Path, force: bool = False) -> None:
    ensure_parent(csv_path)
    if csv_path.exists() and not force:
        print(f"[{now_str()}] skip init (already exists): {csv_path}")
        return

    sample_rows = [
        {
            "product_code": "BCR",
            "product_name": "Bay cat ron",
            "caption": "Bay cat ron ben dep, thi cong nhanh gon.",
            "hashtags": "#baycatron|#dungcuxaydung|#xaydung",
            "weight": "3",
            "active": "1",
        },
        {
            "product_code": "MKRC",
            "product_name": "Mang keo rang cua",
            "caption": "Mang keo rang cua giup dan keo deu, tiet kiem vat tu.",
            "hashtags": "#mangkeorangcua|#oplat|#thicong",
            "weight": "3",
            "active": "1",
        },
        {
            "product_code": "DEFAULT",
            "product_name": "General",
            "caption": "Dung cu chat luong cho cong trinh ben dep.",
            "hashtags": "#dungcuxaydung|#thicong|#xaydung",
            "weight": "1",
            "active": "1",
        },
    ]

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(sample_rows)

    print(f"[{now_str()}] initialized: {csv_path}")


def add_row(
    csv_path: Path,
    code: str,
    product_name: str,
    caption: str,
    hashtags: str,
    weight: int,
    active: int,
) -> None:
    ensure_parent(csv_path)
    if not csv_path.exists():
        init_csv(csv_path, force=False)

    row = {
        "product_code": normalize_code(code),
        "product_name": (product_name or "").strip(),
        "caption": (caption or "").strip(),
        "hashtags": (hashtags or "").strip(),
        "weight": str(max(1, min(100, int(weight)))),
        "active": "1" if int(active) else "0",
    }

    if not row["caption"]:
        raise RuntimeError("caption is required")

    with csv_path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writerow(row)

    print(f"[{now_str()}] added row to {csv_path}: code={row['product_code']}")


def load_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"missing csv file: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise RuntimeError("csv has no header")
        missing = [k for k in CSV_FIELDS if k not in reader.fieldnames]
        if missing:
            raise RuntimeError(f"csv missing columns: {', '.join(missing)}")
        return [dict(row) for row in reader]


def build_bank(csv_path: Path, json_path: Path) -> dict[str, Any]:
    rows = load_csv_rows(csv_path)
    bank: dict[str, dict[str, Any]] = {}
    kept_rows = 0

    for idx, row in enumerate(rows, start=2):
        if not parse_bool(row.get("active", ""), default=True):
            continue

        caption = (row.get("caption", "") or "").strip()
        if not caption:
            continue

        code = normalize_code(row.get("product_code", "DEFAULT") or "DEFAULT")
        name = (row.get("product_name", "") or "").strip()
        hashtags = parse_hashtags(row.get("hashtags", "") or "")
        weight = parse_weight(row.get("weight", ""), default=1)
        item_id = stable_caption_id(code, caption, hashtags)

        entry = bank.setdefault(
            code,
            {
                "product_name": name,
                "items": [],
            },
        )
        if not entry["product_name"] and name:
            entry["product_name"] = name

        entry["items"].append(
            {
                "id": item_id,
                "caption": caption,
                "hashtags": hashtags,
                "weight": weight,
                "source_row": idx,
            }
        )
        kept_rows += 1

    if "DEFAULT" not in bank:
        bank["DEFAULT"] = {"product_name": "General", "items": []}

    payload = {
        "meta": {
            "generated_at": now_str(),
            "source_csv": str(csv_path),
            "total_codes": len(bank),
            "total_captions": kept_rows,
        },
        "codes": bank,
    }

    ensure_parent(json_path)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(
        f"[{now_str()}] built bank: {json_path} "
        f"(codes={payload['meta']['total_codes']}, captions={kept_rows})"
    )
    return payload


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def resolve_product_code(video_name: str, codes: list[str]) -> str | None:
    stem = Path(video_name).stem.upper()
    # Phase 1: strict boundary match first.
    for code in sorted(codes, key=len, reverse=True):
        if code == "DEFAULT":
            continue
        pattern = rf"(?<![A-Z0-9]){re.escape(code)}(?![A-Z0-9])"
        if re.search(pattern, stem):
            return code
    # Phase 2: fallback contains.
    for code in sorted(codes, key=len, reverse=True):
        if code == "DEFAULT":
            continue
        if code in stem:
            return code
    return None


def weighted_pick(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    for it in items:
        total += max(1, int(it.get("weight", 1)))
    if total <= 0:
        return random.choice(items)
    hit = random.uniform(0, float(total))
    acc = 0.0
    for it in items:
        acc += float(max(1, int(it.get("weight", 1))))
        if hit <= acc:
            return it
    return items[-1]


def ensure_bank_ready(csv_path: Path, json_path: Path, auto_build_if_stale: bool) -> None:
    if not auto_build_if_stale:
        if not json_path.exists():
            raise FileNotFoundError(f"missing bank json: {json_path}")
        return

    if not csv_path.exists():
        if not json_path.exists():
            raise FileNotFoundError(
                f"missing both csv and json: csv={csv_path} json={json_path}"
            )
        return

    need_build = False
    if not json_path.exists():
        need_build = True
    else:
        need_build = csv_path.stat().st_mtime > json_path.stat().st_mtime

    if need_build:
        print(f"[{now_str()}] caption bank is stale; rebuilding from csv")
        build_bank(csv_path, json_path)


def validate_rows(rows: list[dict[str, str]], max_chars: int) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    active_counts: dict[str, int] = {}
    seen_caption_key: dict[tuple[str, str], int] = {}
    total_rows = len(rows)
    active_rows = 0

    for idx, row in enumerate(rows, start=2):
        code_raw = row.get("product_code", "") or ""
        code = normalize_code(code_raw)
        caption = (row.get("caption", "") or "").strip()
        active = parse_bool(row.get("active", ""), default=True)
        hashtags = parse_hashtags(row.get("hashtags", "") or "")

        if active:
            active_rows += 1
            active_counts[code] = active_counts.get(code, 0) + 1

        if active and not caption:
            errors.append(f"row {idx}: active=1 but caption is empty")
            continue

        if active and not hashtags:
            warnings.append(f"row {idx}: no hashtags for active caption")

        if not code_raw.strip():
            warnings.append(f"row {idx}: empty product_code (normalized to DEFAULT)")

        if active and caption:
            norm_caption = re.sub(r"\s+", " ", caption).strip().lower()
            key = (code, norm_caption)
            if key in seen_caption_key:
                first_row = seen_caption_key[key]
                warnings.append(
                    f"row {idx}: duplicate caption for code={code} (first seen row {first_row})"
                )
            else:
                seen_caption_key[key] = idx

            if max_chars > 0 and len(caption) > max_chars:
                warnings.append(
                    f"row {idx}: caption length {len(caption)} exceeds max-chars={max_chars}"
                )

        weight_raw = (row.get("weight", "") or "").strip()
        if weight_raw:
            try:
                w = int(weight_raw)
                if w < 1 or w > 100:
                    warnings.append(f"row {idx}: weight={w} out of recommended range 1..100")
            except ValueError:
                warnings.append(f"row {idx}: invalid weight '{weight_raw}' (using default=1)")

    if active_counts.get("DEFAULT", 0) <= 0:
        errors.append("missing active DEFAULT caption (fallback required)")

    return {
        "total_rows": total_rows,
        "active_rows": active_rows,
        "codes": dict(sorted(active_counts.items())),
        "errors": errors,
        "warnings": warnings,
    }


def compose_caption_text(base_caption: str, hashtags: list[str], max_chars: int) -> tuple[str, list[str]]:
    base = (base_caption or "").strip()
    tags = list(hashtags or [])

    def merged_text(caption: str, htags: list[str]) -> str:
        hash_block = " ".join(htags).strip()
        if hash_block:
            return f"{caption}\n{hash_block}" if caption else hash_block
        return caption

    if max_chars <= 0:
        return merged_text(base, tags), tags

    while tags:
        candidate = merged_text(base, tags)
        if len(candidate) <= max_chars:
            return candidate, tags
        tags.pop()

    if len(base) <= max_chars:
        return base, []

    clipped = base[:max_chars].rstrip()
    return clipped, []


def pick_caption(
    bank_path: Path,
    history_path: Path,
    *,
    product_code: str | None,
    video_name: str | None,
    strict_code: bool,
    recent_window: int,
    min_hashtags: int,
    max_hashtags: int,
    max_chars: int,
) -> dict[str, Any]:
    bank = load_json(bank_path, default=None)
    if not bank or "codes" not in bank:
        raise RuntimeError(f"invalid/missing bank json: {bank_path}")

    code_map: dict[str, Any] = bank["codes"]
    all_codes = list(code_map.keys())

    selected_code = None
    if product_code:
        c = normalize_code(product_code)
        if c in code_map:
            selected_code = c
        elif strict_code:
            raise RuntimeError(f"product code not found in bank: {c}")
    if selected_code is None and video_name:
        selected_code = resolve_product_code(video_name, all_codes)
        if selected_code is None and strict_code:
            raise RuntimeError(f"cannot detect product code from video name: {video_name}")
    if selected_code is None:
        selected_code = "DEFAULT" if "DEFAULT" in code_map else all_codes[0]

    candidates = list(code_map.get(selected_code, {}).get("items", []))
    if not candidates and selected_code != "DEFAULT":
        candidates = list(code_map.get("DEFAULT", {}).get("items", []))
        selected_code = "DEFAULT"
    if not candidates:
        raise RuntimeError(f"no active captions for code={selected_code}")

    history = load_json(history_path, default={"updated_at": "", "codes": {}})
    code_history = list(history.get("codes", {}).get(selected_code, {}).get("recent", []))
    recent_set = set(code_history[: max(0, recent_window)])

    filtered = [it for it in candidates if it.get("id") not in recent_set]
    if not filtered:
        filtered = candidates

    item = weighted_pick(filtered)
    full_tags = list(item.get("hashtags", []))
    if not full_tags:
        chosen_tags: list[str] = []
    else:
        lo = max(0, min(min_hashtags, len(full_tags)))
        hi = max(lo, min(max_hashtags, len(full_tags)))
        k = random.randint(lo, hi) if hi > 0 else 0
        chosen_tags = random.sample(full_tags, k=k) if k > 0 else []

    base_caption = str(item.get("caption", "")).strip()
    final_text, chosen_tags = compose_caption_text(base_caption, chosen_tags, max_chars=max_chars)

    new_recent = [item["id"]] + code_history
    new_recent = new_recent[: max(1, recent_window * 3)]
    history.setdefault("codes", {})
    history["codes"][selected_code] = {"recent": new_recent}
    history["updated_at"] = now_str()
    save_json(history_path, history)

    result = {
        "picked_at": now_str(),
        "product_code": selected_code,
        "caption_id": item.get("id"),
        "caption": base_caption,
        "hashtags": chosen_tags,
        "final_text": final_text,
        "final_length": len(final_text),
    }
    return result


def cmd_init(args: argparse.Namespace) -> int:
    init_csv(Path(args.csv), force=args.force)
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    add_row(
        csv_path=Path(args.csv),
        code=args.code,
        product_name=args.name,
        caption=args.caption,
        hashtags=args.hashtags,
        weight=args.weight,
        active=args.active,
    )
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    build_bank(Path(args.csv), Path(args.json))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    rows = load_csv_rows(Path(args.csv))
    summary = validate_rows(rows, max_chars=args.max_chars)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if summary["errors"]:
        return 2
    if args.fail_on_warning and summary["warnings"]:
        return 1
    return 0


def cmd_pick(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv)
    json_path = Path(args.json)
    ensure_bank_ready(csv_path, json_path, auto_build_if_stale=(not args.no_autobuild))

    if args.validate_before_pick and csv_path.exists():
        summary = validate_rows(load_csv_rows(csv_path), max_chars=args.max_chars)
        if summary["errors"]:
            joined = "; ".join(summary["errors"][:5])
            raise RuntimeError(f"caption data validation failed: {joined}")

    result = pick_caption(
        bank_path=json_path,
        history_path=Path(args.history),
        product_code=args.code,
        video_name=args.video,
        strict_code=args.strict_code,
        recent_window=args.recent_window,
        min_hashtags=args.min_hashtags,
        max_hashtags=args.max_hashtags,
        max_chars=args.max_chars,
    )
    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)
    if args.out:
        out_path = Path(args.out)
        ensure_parent(out_path)
        out_path.write_text(output + "\n", encoding="utf-8")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Caption bank manager for TT scripts")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Create caption_master.csv template")
    p_init.add_argument("--csv", default=str(DEFAULT_CSV))
    p_init.add_argument("--force", action="store_true", help="Overwrite existing template")
    p_init.set_defaults(func=cmd_init)

    p_add = sub.add_parser("add", help="Append one caption row to CSV")
    p_add.add_argument("--csv", default=str(DEFAULT_CSV))
    p_add.add_argument("--code", required=True, help="Product code, e.g. BCR")
    p_add.add_argument("--name", default="", help="Product name")
    p_add.add_argument("--caption", required=True, help="Caption text")
    p_add.add_argument("--hashtags", default="", help="Hashtags separated by | , or ;")
    p_add.add_argument("--weight", type=int, default=1, help="Weight 1..100")
    p_add.add_argument("--active", type=int, default=1, choices=[0, 1], help="1=enabled, 0=disabled")
    p_add.set_defaults(func=cmd_add)

    p_build = sub.add_parser("build", help="Build caption_bank.json from CSV")
    p_build.add_argument("--csv", default=str(DEFAULT_CSV))
    p_build.add_argument("--json", default=str(DEFAULT_JSON))
    p_build.set_defaults(func=cmd_build)

    p_validate = sub.add_parser("validate", help="Validate caption CSV quality")
    p_validate.add_argument("--csv", default=str(DEFAULT_CSV))
    p_validate.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help="Soft max text length for one caption line",
    )
    p_validate.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return exit code 1 when warnings exist",
    )
    p_validate.set_defaults(func=cmd_validate)

    p_pick = sub.add_parser("pick", help="Pick random caption by product code/video name")
    p_pick.add_argument("--csv", default=str(DEFAULT_CSV), help="CSV source (used for stale-check/validate)")
    p_pick.add_argument("--json", default=str(DEFAULT_JSON))
    p_pick.add_argument("--history", default=str(DEFAULT_HISTORY))
    p_pick.add_argument("--code", default=None, help="Explicit product code override")
    p_pick.add_argument("--video", default=None, help="Video file name/path for code detection")
    p_pick.add_argument(
        "--strict-code",
        action="store_true",
        help="Fail if product code is missing/unresolved instead of fallback DEFAULT",
    )
    p_pick.add_argument("--recent-window", type=int, default=5, help="Avoid recent repeats per code")
    p_pick.add_argument("--min-hashtags", type=int, default=2)
    p_pick.add_argument("--max-hashtags", type=int, default=4)
    p_pick.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help="Hard cap for final caption text length",
    )
    p_pick.add_argument(
        "--no-autobuild",
        action="store_true",
        help="Disable auto-rebuild when CSV is newer than JSON",
    )
    p_pick.add_argument(
        "--validate-before-pick",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Validate CSV before pick (default: enabled)",
    )
    p_pick.add_argument("--out", default=None, help="Optional output json file path")
    p_pick.set_defaults(func=cmd_pick)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    try:
        configure_stdio_utf8()
        raise SystemExit(main())
    except Exception as exc:
        print(f"[{now_str()}] FAILED: {exc}", file=sys.stderr)
        raise
