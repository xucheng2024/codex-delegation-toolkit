#!/usr/bin/env python3
"""Select the first model from bounded structural evidence without invoking a model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from classify_complexity import ComplexityError, classify
from route_step import RouteError, load_role_map


OUTPUT_SCHEMA = "codex-entry-model-selection-v1"


def select(
    A: Any,
    B: Any,
    U: Any,
    *,
    preflight_complete: bool,
    evidence_truncated: bool,
    available: set[str],
    roles: dict[str, str],
    sol_pin: bool = False,
    terra_permit: bool = False,
) -> dict[str, Any]:
    """Return a deterministic first-model choice and deferred parallel policy."""
    classification = classify(
        A,
        B,
        U,
        preflight_complete=preflight_complete,
        evidence_truncated=evidence_truncated,
        sol_pin=sol_pin,
        terra_permit=terra_permit,
    )
    role = classification["entry_role"]
    model = roles.get(role)
    if model is None:
        return {
            "schema": OUTPUT_SCHEMA,
            "status": "needs_input",
            "role": role,
            "model": None,
            "effort": "medium",
            "classification": classification,
            "parallel_policy": "none",
            "reason": f"{role} role is not configured",
        }
    if model not in available:
        return {
            "schema": OUTPUT_SCHEMA,
            "status": "needs_input",
            "role": role,
            "model": model,
            "effort": "medium",
            "classification": classification,
            "parallel_policy": "none",
            "reason": "selected entry model is unavailable",
        }
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "selected",
        "role": role,
        "model": model,
        "effort": "medium",
        "classification": classification,
        "parallel_policy": "none",
    }


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role-map", type=Path, default=here.parent / "references" / "model-role-map.json")
    parser.add_argument("--A", type=int, required=True, dest="a")
    parser.add_argument("--B", type=int, required=True, dest="b")
    parser.add_argument("--U", type=int, required=True, dest="u")
    parser.add_argument("--preflight-complete", action="store_true")
    parser.add_argument("--evidence-truncated", action="store_true")
    parser.add_argument("--sol-pin", action="store_true")
    parser.add_argument("--terra-permit", action="store_true")
    parser.add_argument("--available", nargs="+", required=True)
    args = parser.parse_args(argv)
    try:
        roles = load_role_map(args.role_map)
        output = select(
            args.a,
            args.b,
            args.u,
            preflight_complete=args.preflight_complete,
            evidence_truncated=args.evidence_truncated,
            sol_pin=args.sol_pin,
            terra_permit=args.terra_permit,
            available=set(args.available),
            roles=roles,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ComplexityError, RouteError) as exc:
        print(json.dumps({"schema": OUTPUT_SCHEMA, "status": "invalid", "error": str(exc)}))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0 if output["status"] == "selected" else 3


if __name__ == "__main__":
    sys.exit(main())
