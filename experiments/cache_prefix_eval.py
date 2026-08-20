#!/usr/bin/env python3
"""Measure five task-specific suffixes sharing one canonical review prefix."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.handoff_input_ab import cache_usage, load_renderer

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
    usage: dict[str, object] = {}
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed":
            raw = event.get("usage", {})
            if isinstance(raw, dict):
                usage = raw
    if result.returncode != 0:
        print(
            f"codex exec failed exit={result.returncode} stderr={result.stderr[:800]!r}",
            flush=True,
        )
    return {
        "exit_code": result.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "usage": usage,
        "cache": cache_usage(usage),
        "visible_chars": len(answer.read_text(encoding="utf-8")) if answer.exists() else 0,
    }


def run() -> list[dict[str, object]]:
    renderer = load_renderer()
    rows = []
    for name, invariant, path, delta in CASES:
        packet = {"invariant": invariant, "changed_files": [path], "diff": delta}
        prompt = renderer.render_packet("review", packet)
        row = {"case": name, **call(prompt, OUT / name)}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    (OUT / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rows


if __name__ == "__main__":
    run()
