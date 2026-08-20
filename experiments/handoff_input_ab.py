#!/usr/bin/env python3
"""Control vs treatment input-handoff A/B: cheap counts, optional live cache probe."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/render_cache_handoff.py"
OUT = ROOT / "experiments" / "handoff_input_ab_results" / time.strftime("%Y%m%dT%H%M%S")
MODEL = "gpt-5.6-sol"
EFFORT = "medium"
CODEX_HOME: Path | None = None
CODEX_PROFILE: str | None = None
FILLER = "None — independent review of the diff only"
LIVE_KEYS = ("scope", "constraints_risks", "acceptance", "anchors")
FILL_KEYS = (
    "history_scope",
    "budget_tier",
    "user_request",
    "objective",
    "deliverable",
    "evidence",
    "parent_hypothesis",
    "retrieve_escalate",
)
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
DEFECT_MARKERS = {
    "auth_default": ("admin",),
    "migration_backfill": ("cents",),
    "race_condition": ("enqueue",),
    "api_compat": ("string",),
    "rounding": ("float",),
}


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_cache_handoff", RENDERER)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load render_cache_handoff.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_fields(invariant: str, diff: str) -> dict[str, str]:
    path = "unknown"
    for line in diff.splitlines():
        if line.startswith("diff --git a/"):
            path = line.split(" a/", 1)[1].split(" ", 1)[0]
            break
    return {
        "scope": f"{path}; do not review unstated code",
        "constraints_risks": invariant,
        "acceptance": "Report every material violation of the invariant. Do not approve if the diff can break it.",
        "anchors": diff.strip(),
    }


def control_packet(invariant: str, diff: str) -> dict[str, str]:
    packet = live_fields(invariant, diff)
    for key in FILL_KEYS:
        packet[key] = FILLER
    return packet


def treatment_packet(invariant: str, diff: str) -> dict[str, str]:
    return live_fields(invariant, diff)


def required_fields_present(packet: dict[str, str], invariant: str, diff: str) -> bool:
    if any(not packet.get(key) for key in LIVE_KEYS):
        return False
    if invariant not in packet["constraints_risks"]:
        return False
    return "diff --git" in packet["anchors"] and diff.strip() in packet["anchors"]


def legacy_review_prompt(renderer: Any, packet: dict[str, str]) -> str:
    return renderer.PREFIXES["review"] + json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def cheap_ab() -> dict[str, Any]:
    renderer = load_renderer()
    rows = []
    passed = True
    for name, invariant, diff in CASES:
        control = control_packet(invariant, diff)
        treatment = treatment_packet(invariant, diff)
        control_prompt = legacy_review_prompt(renderer, control)
        treatment_prompt = renderer.render_packet("review", treatment)
        smaller = len(treatment_prompt.encode("utf-8")) < len(control_prompt.encode("utf-8"))
        required = required_fields_present(treatment, invariant, diff)
        if not smaller or not required:
            passed = False
        rows.append({
            "case": name,
            "control_bytes": len(control_prompt.encode("utf-8")),
            "treatment_bytes": len(treatment_prompt.encode("utf-8")),
            "control_keys": sorted(control),
            "treatment_keys": sorted(treatment),
            "treatment_smaller": smaller,
            "required_fields_present": required,
        })
    return {"gate": 1, "pass": passed, "cases": rows}


def _first_int(*values: object) -> int | None:
    for value in values:
        if isinstance(value, int):
            return value
    return None


def cache_usage(usage: dict[str, Any]) -> dict[str, int | None]:
    details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    if not isinstance(details, dict):
        details = {}
    return {
        "input_tokens": _first_int(usage.get("input_tokens"), usage.get("prompt_tokens")),
        "cached_tokens": _first_int(
            details.get("cached_tokens"),
            usage.get("cached_tokens"),
            usage.get("cached_input_tokens"),
        ),
        "cache_write_tokens": _first_int(
            details.get("cache_write_tokens"),
            usage.get("cache_write_tokens"),
            usage.get("cache_write_input_tokens"),
        ),
    }


def classify_probe(
    warmup_cached: int | None,
    second_input: int | None,
    second_cached: int | None,
    prefix_bytes: int,
    prompt_bytes: int,
    warmup_write: int | None = None,
    second_write: int | None = None,
) -> str:
    if None in (warmup_cached, second_input, second_cached):
        return "inconclusive"
    if warmup_cached == 0 and second_cached == 0:
        if (
            isinstance(warmup_write, int)
            and warmup_write > 0
            and isinstance(second_write, int)
            and second_write > 0
        ):
            return "diagnosis_holds"
        return "inconclusive"
    uncached = second_input - second_cached
    json_est = max(1, (prompt_bytes - prefix_bytes) // 4)
    prefix_est = max(1, prefix_bytes // 4)
    if uncached <= json_est + json_est // 2 + 32 and second_cached >= prefix_est:
        return "diagnosis_wrong"
    if uncached >= prefix_est + (json_est * 7) // 10:
        return "diagnosis_holds"
    return "inconclusive"


def status_line(answer: str) -> str:
    for line in answer.splitlines():
        stripped = line.strip()
        if stripped.startswith("STATUS:"):
            return stripped
    return ""


def defect_found(name: str, answer: str) -> bool:
    status = status_line(answer)
    if not status:
        return False
    body = status.split("STATUS:", 1)[1].strip()
    if body == "APPROVE":
        return False
    lowered = answer.lower()
    return all(marker in lowered for marker in DEFECT_MARKERS[name])


def _call(prompt: str, directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    answer = directory / "answer.md"
    command = ["codex"]
    if CODEX_PROFILE:
        command.extend(["-p", CODEX_PROFILE])
    command.extend([
        "exec", "--json", "--sandbox", "read-only", "--model", MODEL,
        "-c", f'model_reasoning_effort="{EFFORT}"', "--output-last-message", str(answer), "-",
    ])
    env = dict(os.environ)
    if CODEX_HOME is not None:
        env["CODEX_HOME"] = str(CODEX_HOME)
    print(
        f"codex exec start home={env.get('CODEX_HOME', '')!r} profile={CODEX_PROFILE!r} "
        f"model={MODEL} dir={directory}",
        flush=True,
    )
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, input=prompt, text=True, capture_output=True, timeout=1200, env=env)
    (directory / "events.jsonl").write_text(result.stdout, encoding="utf-8")
    (directory / "prompt.md").write_text(prompt, encoding="utf-8")
    usage: dict[str, Any] = {}
    error = None
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed":
            raw = event.get("usage", {})
            if isinstance(raw, dict):
                usage = raw
        if event.get("type") in {"error", "turn.failed"} and error is None:
            payload = event.get("error") if isinstance(event.get("error"), dict) else {}
            error = event.get("message") or payload.get("message")
    text = answer.read_text(encoding="utf-8") if answer.exists() else result.stderr
    if result.returncode != 0:
        (directory / "stderr.txt").write_text(result.stderr, encoding="utf-8")
        print(
            f"codex exec failed exit={result.returncode} error={error!r} "
            f"stderr={result.stderr[:800]!r}",
            flush=True,
        )
    return {
        "exit_code": result.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "usage": usage,
        "cache": cache_usage(usage),
        "error": error,
        "answer": text,
        "visible_chars": len(text),
    }


def live_probe(out: Path | None = None) -> dict[str, Any]:
    renderer = load_renderer()
    directory = out or OUT
    auth = CASES[0]
    rounding = CASES[4]
    control_auth = legacy_review_prompt(renderer, control_packet(auth[1], auth[2]))
    control_rounding = legacy_review_prompt(renderer, control_packet(rounding[1], rounding[2]))
    treatment_rounding = renderer.render_packet("review", treatment_packet(rounding[1], rounding[2]))
    warmup = {"step": "warmup_control_auth", **_call(control_auth, directory / "probe" / "warmup")}
    second = {"step": "control_rounding", **_call(control_rounding, directory / "probe" / "control")}
    third = {"step": "treatment_rounding", **_call(treatment_rounding, directory / "probe" / "treatment")}
    prefix_bytes = len(renderer.PREFIXES["review"].encode("utf-8"))
    verdict = classify_probe(
        warmup["cache"]["cached_tokens"],
        second["cache"]["input_tokens"],
        second["cache"]["cached_tokens"],
        prefix_bytes,
        len(control_rounding.encode("utf-8")),
        warmup["cache"]["cache_write_tokens"],
        second["cache"]["cache_write_tokens"],
    )
    compact = (
        isinstance(third["cache"]["input_tokens"], int)
        and isinstance(second["cache"]["input_tokens"], int)
        and third["cache"]["input_tokens"] < second["cache"]["input_tokens"]
    )
    rows = []
    for row in (warmup, second, third):
        rows.append({key: value for key, value in row.items() if key != "answer"})
    return {
        "gate": 2,
        "verdict": verdict,
        "treatment_input_smaller": compact,
        "prefix_bytes": prefix_bytes,
        "calls": rows,
    }


def quality_pair(out: Path | None = None) -> dict[str, Any]:
    renderer = load_renderer()
    directory = out or OUT
    rows = []
    control_found = 0
    treatment_found = 0
    extra_approve = False
    for name, invariant, diff in CASES:
        for arm, packet in (
            ("control", control_packet(invariant, diff)),
            ("treatment", treatment_packet(invariant, diff)),
        ):
            prompt = (
                legacy_review_prompt(renderer, packet)
                if arm == "control"
                else renderer.render_packet("review", packet)
            )
            result = _call(prompt, directory / "quality" / name / arm)
            found = defect_found(name, str(result["answer"]))
            if arm == "control" and found:
                control_found += 1
            if arm == "treatment" and found:
                treatment_found += 1
            if arm == "treatment" and not found and status_line(str(result["answer"])).endswith("APPROVE"):
                extra_approve = True
            rows.append({
                "case": name,
                "arm": arm,
                "defect_found": found,
                "status": status_line(str(result["answer"])),
                **{key: value for key, value in result.items() if key != "answer"},
            })
    passed = treatment_found >= control_found and not extra_approve
    return {
        "gate": 3,
        "pass": passed,
        "control_found": control_found,
        "treatment_found": treatment_found,
        "extra_approve": extra_approve,
        "cases": rows,
    }


def _write(payload: dict[str, Any], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("cheap", "probe", "quality"), default="cheap")
    parser.add_argument("--codex-home", type=Path, default=None)
    parser.add_argument("--profile", default=None)
    args = parser.parse_args()
    global CODEX_HOME, CODEX_PROFILE
    CODEX_HOME = args.codex_home
    CODEX_PROFILE = args.profile
    if args.mode == "cheap":
        payload = cheap_ab()
    elif args.mode == "probe":
        payload = live_probe()
    else:
        payload = quality_pair()
    _write(payload, OUT)
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    if args.mode == "cheap":
        return 0 if payload["pass"] else 1
    if args.mode == "quality":
        return 0 if payload["pass"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
