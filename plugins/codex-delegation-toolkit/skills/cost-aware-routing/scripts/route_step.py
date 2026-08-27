#!/usr/bin/env python3
"""Apply the step routing contract from the bundled role map."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROLE_MAP_SCHEMA = "codex-model-role-map-v1"
STEPS = ("plan", "plan-review", "implement", "judge")
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
    required = ("quality_first", "balanced")
    for role in required:
        model = roles.get(role)
        if not isinstance(model, str) or not model:
            raise RouteError(f"roles.{role} must be a non-empty model id")
    result = {role: str(roles[role]) for role in required}
    economy = roles.get("economy")
    if economy is not None:
        if not isinstance(economy, str) or not economy:
            raise RouteError("roles.economy must be a non-empty model id")
        result["economy"] = economy
    return result


def effort_for(role: str, hard_packet: bool) -> str:
    # First pass is always medium. Post-verifier upgrades use escalate_step.py.
    return "medium"


def decide(
    step: str,
    parent: str,
    sol_pin: bool,
    terra_permit: bool,
    available: set[str],
    roles: dict[str, str],
    bounded: bool = False,
    contract_complete: bool = False,
    hard_packet: bool = False,
    independent_review: bool = False,
    complexity_tier: str | None = None,
    delegation_available: bool = False,
) -> dict[str, Any]:
    if step not in STEPS:
        raise RouteError("step must be plan, plan-review, implement, or judge")
    quality_first = roles["quality_first"]
    balanced = roles["balanced"]
    if complexity_tier not in (None, "fast", "reviewed"):
        raise RouteError("complexity_tier must be fast or reviewed")
    if step == "plan-review":
        # Plan review is always a fresh independent read-only check.
        target, role, actor = quality_first, "quality_first", "spawn"
    elif step == "judge":
        target, role = quality_first, "quality_first"
        actor = "spawn" if independent_review or parent != target else "parent"
    elif step == "plan":
        target, role = quality_first, "quality_first"
    else:
        if complexity_tier == "fast" and not sol_pin and not terra_permit:
            economy = roles.get("economy")
            if parent in (balanced, economy, "current"):
                # Starting another model for a small bounded edit costs more context and
                # latency than finishing with the already-active implementation model.
                target = parent
                role = next(
                    (name for name, model in roles.items() if model == parent),
                    "current",
                )
            else:
                if economy is None:
                    return {
                        "schema": OUTPUT_SCHEMA, "status": "ask", "action": "ask",
                        "role": "economy", "model": None, "effort": "medium",
                        "reason": "economy role is not configured; disclose and ask or explicit degrade",
                    }
                target, role = economy, "economy"
        else:
            target, role = balanced, "balanced"
    if step not in ("plan-review", "judge"):
        actor = "parent" if parent == target else "spawn"
    effort = effort_for(role, hard_packet)
    if target != "current" and target not in available:
        return {
            "schema": OUTPUT_SCHEMA,
            "status": "ask",
            "action": "ask",
            "role": role,
            "model": target,
            "effort": effort,
            "reason": "target unavailable; disclose and ask or explicit degrade",
        }
    if actor == "spawn" and not delegation_available:
        return {
            "schema": OUTPUT_SCHEMA,
            "status": "degraded",
            "action": "parent",
            "role": "fallback_parent",
            "model": parent,
            "effort": effort,
            "spawn": False,
            "requested_role": role,
            "requested_model": target,
            "reason": "delegation transport unavailable; use bounded inline execution or review and never wait",
        }
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "routed",
        "action": actor,
        "role": role,
        "model": target,
        "effort": effort,
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
    parser.add_argument("--bounded", action="store_true")
    parser.add_argument("--contract-complete", action="store_true")
    parser.add_argument("--hard-packet", action="store_true")
    parser.add_argument("--independent-review", action="store_true")
    parser.add_argument("--complexity-tier", choices=("fast", "reviewed"))
    parser.add_argument(
        "--delegation-available",
        action="store_true",
        help="Assert that spawn_agent is callable in this runtime. Omission fails safe to inline work.",
    )
    parser.add_argument("--available", nargs="+", required=True)
    args = parser.parse_args(argv)
    try:
        roles = load_role_map(args.role_map)
        output = decide(
            args.step,
            args.parent,
            args.sol_pin,
            args.terra_permit,
            set(args.available),
            roles,
            args.bounded,
            args.contract_complete,
            args.hard_packet,
            args.independent_review,
            args.complexity_tier,
            args.delegation_available,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RouteError) as exc:
        print(json.dumps({"schema": OUTPUT_SCHEMA, "status": "invalid", "error": str(exc)}))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0 if output["status"] in ("routed", "degraded") else 3


if __name__ == "__main__":
    sys.exit(main())
