#!/usr/bin/env python3
"""Escalate implement compute only after a deterministic verifier fails."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from route_step import OUTPUT_SCHEMA, RouteError, STEPS, load_role_map


VERIFIERS = ("pass", "fail", "incomplete")
EFFORTS = ("medium", "high")


def decide(
    step: str,
    current_effort: str,
    verifier: str,
    parent: str,
    available: set[str],
    roles: dict[str, str],
) -> dict[str, Any]:
    if step not in STEPS:
        raise RouteError("step must be plan, implement, or judge")
    if current_effort not in EFFORTS:
        raise RouteError("current-effort must be medium or high")
    if verifier not in VERIFIERS:
        raise RouteError("verifier must be pass, fail, or incomplete")

    sol = roles["quality_first"]
    terra = roles["balanced"]
    if verifier == "pass" or step != "implement":
        return {
            "schema": OUTPUT_SCHEMA,
            "status": "routed",
            "action": "stop",
            "role": "balanced" if step == "implement" else "quality_first",
            "model": parent,
            "effort": current_effort,
            "step": step,
            "spawn": False,
        }

    if current_effort == "medium":
        target, role, effort, actor = terra, "balanced", "high", "retry"
        spawn = parent != terra
        next_step = "implement"
    else:
        target, role, effort, actor = sol, "quality_first", "medium", "spawn"
        spawn = True
        next_step = "judge"

    if target not in available:
        return {
            "schema": OUTPUT_SCHEMA,
            "status": "ask",
            "action": "ask",
            "role": role,
            "model": target,
            "effort": effort,
            "step": next_step,
            "spawn": False,
            "reason": "target unavailable; disclose and ask or explicit degrade",
        }
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "routed",
        "action": actor,
        "role": role,
        "model": target,
        "effort": effort,
        "step": next_step,
        "spawn": spawn,
    }


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role-map", type=Path, default=here.parent / "references" / "model-role-map.json")
    parser.add_argument("--step", choices=STEPS, required=True)
    parser.add_argument("--current-effort", choices=EFFORTS, required=True)
    parser.add_argument("--verifier", choices=VERIFIERS, required=True)
    parser.add_argument("--parent", required=True)
    parser.add_argument("--available", nargs="+", required=True)
    args = parser.parse_args(argv)
    try:
        roles = load_role_map(args.role_map)
        output = decide(args.step, args.current_effort, args.verifier, args.parent, set(args.available), roles)
    except (OSError, UnicodeError, json.JSONDecodeError, RouteError) as exc:
        print(json.dumps({"schema": OUTPUT_SCHEMA, "status": "invalid", "error": str(exc)}))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0 if output["status"] == "routed" else 3


if __name__ == "__main__":
    sys.exit(main())
