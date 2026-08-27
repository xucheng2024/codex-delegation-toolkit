#!/usr/bin/env python3
"""Record privacy-safe adaptive-compute events for later replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "codex-compute-event-v1"
WORKFLOW_SCHEMA = "codex-workflow-outcome-v1"
STEPS = ("decompose", "implement", "judge")
EFFORTS = ("medium", "high")
VERIFIERS = ("pass", "fail", "incomplete")
ACTIONS = ("stop", "retry_high", "spawn_sol_judge")
SUCCESSES = ("pass", "fail", "unknown")
COMPLEXITY_BUCKETS = ("fast", "reviewed")
POLICIES = ("single", "dag")
MODEL_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


class RecordError(ValueError):
    """Raised when an event cannot be stored safely."""


def cache_dir() -> Path:
    override = os.environ.get("COST_AWARE_ROUTING_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    return codex_home / "cache" / "cost-aware-routing"


def events_path() -> Path:
    return cache_dir() / "events.jsonl"


def workflows_path() -> Path:
    return cache_dir() / "workflows.jsonl"


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


def _optional_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RecordError(f"{field} must be a non-negative integer")
    return value


def _optional_cost(value: Any) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise RecordError("cost_usd must be a non-negative number")
    return float(value)


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RecordError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RecordError(f"{field} must be a non-negative integer")
    return value


def _nonnegative_finite_number(value: Any, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise RecordError(f"{field} must be a finite non-negative number")
    return float(value)


def record(
    step: str,
    model: str,
    effort: str,
    verifier: str,
    action: str,
    success: str = "unknown",
    *,
    hard_packet: bool = False,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    latency_ms: int | None = None,
    cost_usd: float | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    if step not in STEPS:
        raise RecordError("step must be decompose, implement, or judge")
    if not isinstance(model, str) or not MODEL_RE.fullmatch(model):
        raise RecordError("model must be a short identifier")
    if effort not in EFFORTS:
        raise RecordError("effort must be medium or high")
    if verifier not in VERIFIERS:
        raise RecordError("verifier must be pass, fail, or incomplete")
    if action not in ACTIONS:
        raise RecordError("action must be stop, retry_high, or spawn_sol_judge")
    if success not in SUCCESSES:
        raise RecordError("success must be pass, fail, or unknown")
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": repo_key(cwd),
        "step": step,
        "model": model,
        "effort": effort,
        "verifier": verifier,
        "action": action,
        "success": success,
        "hard_packet": bool(hard_packet),
    }
    optional = {
        "input_tokens": _optional_int(input_tokens, "input_tokens"),
        "output_tokens": _optional_int(output_tokens, "output_tokens"),
        "reasoning_tokens": _optional_int(reasoning_tokens, "reasoning_tokens"),
        "latency_ms": _optional_int(latency_ms, "latency_ms"),
        "cost_usd": _optional_cost(cost_usd),
    }
    payload.update({key: value for key, value in optional.items() if value is not None})
    path = events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return payload


def record_workflow(
    complexity_bucket: str,
    policy: str,
    task_count: int,
    dependency_count: int,
    critical_path_length: int,
    total_cost_units: float,
    total_latency_ms: int,
    final_pass: bool,
    rework_count: int,
    *,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Append one fixed-shape, privacy-safe workflow outcome."""
    if complexity_bucket not in COMPLEXITY_BUCKETS:
        raise RecordError("complexity_bucket must be fast or reviewed")
    if policy not in POLICIES:
        raise RecordError("policy must be single or dag")
    task_count = _positive_int(task_count, "task_count")
    dependency_count = _nonnegative_int(dependency_count, "dependency_count")
    critical_path_length = _positive_int(critical_path_length, "critical_path_length")
    if critical_path_length > task_count:
        raise RecordError("critical_path_length must not exceed task_count")
    total_cost_units = _nonnegative_finite_number(total_cost_units, "total_cost_units")
    total_latency_ms = _nonnegative_int(total_latency_ms, "total_latency_ms")
    if not isinstance(final_pass, bool):
        raise RecordError("final_pass must be a boolean")
    rework_count = _nonnegative_int(rework_count, "rework_count")
    payload = {
        "schema": WORKFLOW_SCHEMA,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": repo_key(cwd),
        "complexity_bucket": complexity_bucket,
        "policy": policy,
        "task_count": task_count,
        "dependency_count": dependency_count,
        "critical_path_length": critical_path_length,
        "total_cost_units": total_cost_units,
        "total_latency_ms": total_latency_ms,
        "final_pass": final_pass,
        "rework_count": rework_count,
    }
    path = workflows_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return payload


def load_records() -> list[dict[str, Any]]:
    path = events_path()
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
        if not isinstance(item, dict) or item.get("schema") != SCHEMA or item.get("action") not in ACTIONS:
            continue
        try:
            _optional_cost(item.get("cost_usd"))
        except RecordError:
            continue
        rows.append(item)
    return rows


def format_stats(rows: list[dict[str, Any]], *, cwd: Path | None = None) -> str:
    current = repo_key(cwd)
    scoped = [row for row in rows if row.get("repo") == current]
    actions = Counter(row.get("action") for row in scoped)
    verifiers = Counter(row.get("verifier") for row in scoped)
    lines = [
        f"repo {current}",
        f"events {len(scoped)}",
        " ".join(f"{name}={actions.get(name, 0)}" for name in ACTIONS),
        f"verifier pass={verifiers.get('pass', 0)} fail={verifiers.get('fail', 0)} incomplete={verifiers.get('incomplete', 0)}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    record_parser = sub.add_parser("record", help="Append one privacy-safe compute event")
    record_parser.add_argument("--step", required=True, choices=STEPS)
    record_parser.add_argument("--model", required=True)
    record_parser.add_argument("--effort", required=True, choices=EFFORTS)
    record_parser.add_argument("--verifier", required=True, choices=VERIFIERS)
    record_parser.add_argument("--action", required=True, choices=ACTIONS)
    record_parser.add_argument("--success", default="unknown", choices=SUCCESSES)
    record_parser.add_argument("--hard-packet", action="store_true")
    record_parser.add_argument("--input-tokens", type=int)
    record_parser.add_argument("--output-tokens", type=int)
    record_parser.add_argument("--reasoning-tokens", type=int)
    record_parser.add_argument("--latency-ms", type=int)
    record_parser.add_argument("--cost-usd", type=float)

    workflow_parser = sub.add_parser("record-workflow", help="Append one privacy-safe workflow outcome")
    workflow_parser.add_argument("--complexity-bucket", required=True, choices=COMPLEXITY_BUCKETS)
    workflow_parser.add_argument("--policy", required=True, choices=POLICIES)
    workflow_parser.add_argument("--task-count", required=True, type=int)
    workflow_parser.add_argument("--dependency-count", required=True, type=int)
    workflow_parser.add_argument("--critical-path-length", required=True, type=int)
    workflow_parser.add_argument("--total-cost-units", required=True, type=float)
    workflow_parser.add_argument("--total-latency-ms", required=True, type=int)
    workflow_parser.add_argument("--final-pass", action="store_true")
    workflow_parser.add_argument("--rework-count", required=True, type=int)

    sub.add_parser("stats", help="Show counts for the current repository")
    args = parser.parse_args(argv)

    try:
        if args.command == "record":
            payload = record(
                args.step,
                args.model,
                args.effort,
                args.verifier,
                args.action,
                args.success,
                hard_packet=args.hard_packet,
                input_tokens=args.input_tokens,
                output_tokens=args.output_tokens,
                reasoning_tokens=args.reasoning_tokens,
                latency_ms=args.latency_ms,
                cost_usd=args.cost_usd,
            )
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
            return 0
        if args.command == "record-workflow":
            payload = record_workflow(
                args.complexity_bucket,
                args.policy,
                args.task_count,
                args.dependency_count,
                args.critical_path_length,
                args.total_cost_units,
                args.total_latency_ms,
                args.final_pass,
                args.rework_count,
            )
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
            return 0
        print(format_stats(load_records()), end="")
        return 0
    except RecordError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "invalid", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
