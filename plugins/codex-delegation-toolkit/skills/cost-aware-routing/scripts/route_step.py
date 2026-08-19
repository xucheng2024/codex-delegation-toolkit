#!/usr/bin/env python3
"""Apply the step routing contract from the bundled role map."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROLE_MAP_SCHEMA = "codex-model-role-map-v1"
STEPS = ("implement", "judge")
OUTPUT_SCHEMA = "codex-step-routing-v1"


class RouteError(ValueError):
    """Raised when a step cannot be routed from the role map."""


def load_role_map(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != ROLE_MAP_SCHEMA:
        raise RouteError(f"schema must be {ROLE_MAP_SCHEMA}")
    if "available" in json.dumps(data):
        raise RouteError("role map must not claim availability")
    roles = data.get("roles")
    if not isinstance(roles, dict):
        raise RouteError("roles must be an object")
    required = ("quality_first", "balanced", "economy")
    for role in required:
        model = roles.get(role)
        if not isinstance(model, str) or not model:
            raise RouteError(f"roles.{role} must be a non-empty model id")
    return {role: str(roles[role]) for role in required}


def decide(
    step: str,
    parent: str,
    sol_pin: bool,
    terra_permit: bool,
    available: set[str],
    roles: dict[str, str],
) -> dict[str, Any]:
    if step not in STEPS:
        raise RouteError("step must be implement or judge")
    sol = roles["quality_first"]
    terra = roles["balanced"]
    if sol_pin and not terra_permit:
        target, role = sol, "quality_first"
        actor = "parent" if parent == sol else "spawn"
    elif step == "judge":
        target, role, actor = sol, "quality_first", "spawn"
    elif parent == terra:
        target, role, actor = terra, "balanced", "parent"
    else:
        target, role, actor = terra, "balanced", "spawn"
    if target not in available:
        return {
            "schema": OUTPUT_SCHEMA,
            "status": "ask",
            "action": "ask",
            "role": role,
            "model": target,
            "reason": "target unavailable; disclose and ask or explicit degrade",
        }
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "routed",
        "action": actor,
        "role": role,
        "model": target,
        "spawn": actor == "spawn",
    }


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role-map", type=Path, default=here.parent / "references" / "model-role-map.json")
    parser.add_argument("--step", choices=STEPS, required=True)
    parser.add_argument("--parent", required=True)
    parser.add_argument("--sol-pin", action="store_true")
    parser.add_argument("--terra-permit", action="store_true")
    parser.add_argument("--available", nargs="+", required=True)
    args = parser.parse_args(argv)
    try:
        roles = load_role_map(args.role_map)
        output = decide(args.step, args.parent, args.sol_pin, args.terra_permit, set(args.available), roles)
    except (OSError, UnicodeError, json.JSONDecodeError, RouteError) as exc:
        print(json.dumps({"schema": OUTPUT_SCHEMA, "status": "invalid", "error": str(exc)}))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0 if output["status"] == "routed" else 3


if __name__ == "__main__":
    sys.exit(main())
