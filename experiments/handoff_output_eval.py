#!/usr/bin/env python3
"""Paired five-case Sol review-output compression experiment.

Runs the same supplied diff twice: a normal narrative review and a compact
handoff review. It records Codex-reported usage and visible response length.
It does not claim that provider output tokens are only visible text.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "output_eval_results" / time.strftime("%Y%m%dT%H%M%S")
MODEL = "gpt-5.6-sol"
EFFORT = "medium"

CASES = (
    ("auth_default", "A public API must reject requests without a verified user.", """diff --git a/app/auth.py b/app/auth.py
@@
-    if user is None:
-        raise Unauthorized()
+    if user is None:
+        return GuestUser(admin=True)
"""),
    ("migration_backfill", "A schema migration must preserve existing customer balances.", """diff --git a/db/migrate.py b/db/migrate.py
@@
 def migrate(conn):
     conn.execute("ALTER TABLE accounts ADD COLUMN cents INTEGER NOT NULL DEFAULT 0")
+    conn.execute("UPDATE accounts SET cents = 0")
"""),
    ("race_condition", "At most one reservation may be created for each inventory unit.", """diff --git a/app/reserve.py b/app/reserve.py
@@
 def reserve(unit_id):
     if available(unit_id):
-        return create_reservation(unit_id)
+        enqueue_create_reservation(unit_id)
+        return {"accepted": True}
"""),
    ("api_compat", "Existing clients require the JSON field `id` to remain a string.", """diff --git a/app/serializers.py b/app/serializers.py
@@
-    return {"id": str(order.id), "status": order.status}
+    return {"id": order.id, "status": order.status}
"""),
    ("rounding", "The ledger must use integer cents; no float arithmetic may affect posted amounts.", """diff --git a/app/ledger.py b/app/ledger.py
@@
-    return cents
+    return round(cents / 100.0, 2) * 100
"""),
)

BASELINE_SUFFIX = """Review the supplied diff against the stated invariant. Do not use tools or assume unstated code. Give a clear, detailed review for an engineer deciding whether to merge."""
COMPACT_SUFFIX = """Review the supplied diff against the stated invariant. Do not use tools or assume unstated code. This is an agent-to-agent handoff, not a user explanation. Use terse English and return only:
STATUS: APPROVE | CHANGES_REQUIRED | INCOMPLETE
FINDINGS:
- <severity> <path:line or symbol> | <violated invariant or risk> | <failure mechanism> | <minimum fix>
VALIDATION: <one or two focused checks>
OVERFLOW_REASON: none | <reason>
Do not restate the task or diff. Include every material finding; if safe completeness is impossible, use INCOMPLETE."""


def call(prompt: str, directory: Path) -> dict[str, object]:
    directory.mkdir(parents=True, exist_ok=True)
    answer = directory / "answer.md"
    command = [
        "codex", "exec", "--json", "--ephemeral", "--sandbox", "read-only",
        "--model", MODEL, "-c", f'model_reasoning_effort="{EFFORT}"',
        "--output-last-message", str(answer), "-",
    ]
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, input=prompt, text=True, capture_output=True, timeout=1200)
    elapsed = round(time.monotonic() - started, 3)
    (directory / "events.jsonl").write_text(result.stdout, encoding="utf-8")
    text = answer.read_text(encoding="utf-8") if answer.exists() else result.stderr
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
        "elapsed_seconds": elapsed,
        "usage": usage,
        "visible_chars": len(text),
        "visible_words": len(text.split()),
        "answer": text,
    }


def prompt(invariant: str, diff: str, suffix: str) -> str:
    return f"INVARIANT:\n{invariant}\n\nDIFF:\n{diff}\n\n{suffix}\n"


def run() -> list[dict[str, object]]:
    rows = []
    for name, invariant, diff in CASES:
        for variant, suffix in (("baseline", BASELINE_SUFFIX), ("compact", COMPACT_SUFFIX)):
            result = call(prompt(invariant, diff, suffix), OUT / name / variant)
            rows.append({
                "case": name,
                "variant": variant,
                **{key: value for key, value in result.items() if key != "answer"},
            })
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    (OUT / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rows


if __name__ == "__main__":
    run()
