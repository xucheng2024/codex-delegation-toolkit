#!/usr/bin/env python3
"""Score stop / adaptive / always-high / always-Sol policies on recorded traces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "codex-compute-replay-v1"
ARMS = ("medium", "high", "sol")
POLICIES = ("always_stop", "adaptive", "always_high", "always_sol")
SUCCESSES = ("pass", "fail")


class ReplayError(ValueError):
    """Raised when traces cannot be scored."""


def _arm(raw: Any, field: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ReplayError(f"{field} must be an object")
    verifier = raw.get("verifier")
    success = raw.get("success")
    if verifier not in ("pass", "fail", "incomplete"):
        raise ReplayError(f"{field}.verifier is invalid")
    if success not in SUCCESSES:
        raise ReplayError(f"{field}.success is invalid")
    cost = raw.get("cost_usd")
    if cost is not None and (isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0):
        raise ReplayError(f"{field}.cost_usd must be a non-negative number")
    arm = {"verifier": verifier, "success": success}
    if cost is not None:
        arm["cost_usd"] = float(cost)
    return arm


def load_traces(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ReplayError(f"schema must be {SCHEMA}")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ReplayError("tasks must be a non-empty list")
    loaded = []
    for index, raw in enumerate(tasks):
        if not isinstance(raw, dict):
            raise ReplayError(f"tasks[{index}] must be an object")
        task_id = raw.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise ReplayError(f"tasks[{index}].id must be a non-empty string")
        arms_raw = raw.get("arms")
        if not isinstance(arms_raw, dict):
            raise ReplayError(f"tasks[{index}].arms must be an object")
        arms = {name: _arm(arms_raw.get(name), f"tasks[{index}].arms.{name}") for name in ARMS}
        loaded.append({"id": task_id, "hard_packet": bool(raw.get("hard_packet")), "arms": arms})
    return loaded


def _run_policy(task: dict[str, Any], policy: str) -> dict[str, Any]:
    arms = task["arms"]
    if policy == "always_stop":
        used = [arms["medium"]]
    elif policy == "always_high":
        used = [arms["high"]]
    elif policy == "always_sol":
        used = [arms["sol"]]
    elif policy == "adaptive":
        used = [arms["medium"]]
        if arms["medium"]["verifier"] != "pass":
            used.append(arms["high"])
            if arms["high"]["verifier"] != "pass":
                used.append(arms["sol"])
    else:
        raise ReplayError(f"unknown policy: {policy}")
    costs = [arm["cost_usd"] for arm in used if "cost_usd" in arm]
    return {
        "success": used[-1]["success"] == "pass",
        "upgraded": len(used) > 1,
        "cost_usd": sum(costs) if len(costs) == len(used) else None,
    }


def score_policies(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    policies: dict[str, dict[str, Any]] = {}
    for name in POLICIES:
        rows = [_run_policy(task, name) for task in tasks]
        costs = [row["cost_usd"] for row in rows if row["cost_usd"] is not None]
        result: dict[str, Any] = {
            "tasks": len(rows),
            "success_rate": sum(row["success"] for row in rows) / len(rows),
            "upgrade_rate": sum(row["upgraded"] for row in rows) / len(rows),
        }
        if len(costs) == len(rows):
            result["mean_cost_usd"] = sum(costs) / len(rows)
        policies[name] = result
    return {"schema": SCHEMA, "status": "scored", "policies": policies}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = score_policies(load_traces(args.traces))
    except OSError:
        print(json.dumps({"schema": SCHEMA, "status": "invalid", "error": "traces could not be read"}))
        return 2
    except (UnicodeError, json.JSONDecodeError):
        print(json.dumps({"schema": SCHEMA, "status": "invalid", "error": "traces are not valid UTF-8 JSON"}))
        return 2
    except ReplayError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "invalid", "error": str(exc)}))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
