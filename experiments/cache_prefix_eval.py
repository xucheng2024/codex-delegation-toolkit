#!/usr/bin/env python3
"""Measure five task-specific suffixes sharing one canonical review prefix."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/render_cache_handoff.py"
OUT = ROOT / "experiments" / "cache_prefix_results" / time.strftime("%Y%m%dT%H%M%S")
MODEL = "gpt-5.6-sol"
EFFORT = "medium"

CASES = (
    ("auth", "A public API must reject requests without a verified user.", "app/auth.py", "if user is None: return GuestUser(admin=True)"),
    ("migration", "A schema migration must preserve existing customer balances.", "db/migrate.py", "UPDATE accounts SET cents = 0"),
    ("race", "At most one reservation may exist for each inventory unit.", "app/reserve.py", "if available(unit_id): enqueue_create_reservation(unit_id)"),
    ("compat", "Existing clients require JSON field id to remain a string.", "app/serializers.py", "return {\"id\": order.id}"),
    ("rounding", "The ledger must use integer cents; float arithmetic must not affect posted amounts.", "app/ledger.py", "return round(cents / 100.0, 2) * 100"),
)

PREFIX = """CACHE_HANDOFF_V1
KIND: REVIEW
Review only the supplied delta and report every material correctness, security, compatibility, or contract risk. Do not narrate unchanged code or reopen design exploration.
RESULT:
STATUS: APPROVE | CHANGES_REQUIRED | INCOMPLETE
FINDINGS: <none or severity | anchor | risk | mechanism | minimum fix>
VALIDATION: <focused checks>
OVERFLOW_REASON: none | <reason>
DYNAMIC_PACKET_JSON:
"""


def call(prompt: str, directory: Path) -> dict[str, object]:
    directory.mkdir(parents=True, exist_ok=True)
    answer = directory / "answer.md"
    command = [
        "codex", "exec", "--json", "--sandbox", "read-only", "--model", MODEL,
        "-c", f'model_reasoning_effort="{EFFORT}"', "--output-last-message", str(answer), "-",
    ]
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, input=prompt, text=True, capture_output=True, timeout=1200)
    (directory / "events.jsonl").write_text(result.stdout, encoding="utf-8")
    (directory / "prompt.md").write_text(prompt, encoding="utf-8")
    usage: dict[str, int] = {}
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed":
            usage = event.get("usage", {})
    return {
        "exit_code": result.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "usage": usage,
        "visible_chars": len(answer.read_text(encoding="utf-8")) if answer.exists() else 0,
    }


def run() -> list[dict[str, object]]:
    rows = []
    for name, invariant, path, delta in CASES:
        packet = {"invariant": invariant, "changed_files": [path], "diff": delta}
        prompt = PREFIX + json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        row = {"case": name, **call(prompt, OUT / name)}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    (OUT / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rows


if __name__ == "__main__":
    run()
