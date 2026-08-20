#!/usr/bin/env python3
"""Record privacy-safe Keep Plot outcomes for later stats."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ACTIONS = ("compact", "skip", "veto", "restore")
POST_CHECKS = ("pass", "fail", "na")
REASON_MAX = 80


def cache_dir() -> Path:
    override = os.environ.get("KEEP_PLOT_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    return codex_home / "cache" / "keep-plot"


def outcomes_path() -> Path:
    return cache_dir() / "outcomes.jsonl"


def repo_key(cwd: Path | None = None) -> str:
    working = cwd or Path.cwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=working,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "none"
    root = result.stdout.strip().encode("utf-8")
    if not root:
        return "none"
    return hashlib.sha256(root).hexdigest()[:12]


def sanitize_reason(reason: str) -> str:
    cleaned = " ".join(reason.split())
    return cleaned[:REASON_MAX]


def record(action: str, reason: str, post_check: str, *, cwd: Path | None = None) -> dict:
    if action not in ACTIONS:
        raise SystemExit(f"action must be one of: {', '.join(ACTIONS)}")
    if post_check not in POST_CHECKS:
        raise SystemExit(f"post-check must be one of: {', '.join(POST_CHECKS)}")
    payload = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": repo_key(cwd),
        "action": action,
        "reason": sanitize_reason(reason),
        "post_check": post_check,
    }
    path = outcomes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return payload


def load_records() -> list[dict]:
    path = outcomes_path()
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("action") in ACTIONS:
            rows.append(item)
    return rows


def format_stats(rows: list[dict], *, cwd: Path | None = None) -> str:
    current = repo_key(cwd)
    scoped = [row for row in rows if row.get("repo") == current]
    actions = Counter(row.get("action") for row in scoped)
    checks = Counter(row.get("post_check") for row in scoped)
    lines = [
        f"repo {current}",
        f"events {len(scoped)}",
        " ".join(f"{name}={actions.get(name, 0)}" for name in ACTIONS),
        f"post_check pass={checks.get('pass', 0)} fail={checks.get('fail', 0)} na={checks.get('na', 0)}",
    ]
    if actions.get("restore", 0):
        lines.append("high restore means later checkpoints dropped state")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    record_parser = sub.add_parser("record", help="Append one outcome")
    record_parser.add_argument("--action", required=True, choices=ACTIONS)
    record_parser.add_argument("--reason", default="")
    record_parser.add_argument("--post-check", default="na", choices=POST_CHECKS)

    sub.add_parser("stats", help="Show counts for the current repository")
    args = parser.parse_args()

    if args.command == "record":
        payload = record(args.action, args.reason, args.post_check)
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return 0

    print(format_stats(load_records()), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
