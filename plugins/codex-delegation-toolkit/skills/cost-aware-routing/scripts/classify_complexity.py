#!/usr/bin/env python3
"""Classify structurally evidenced implementation complexity deterministically."""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any


OUTPUT_SCHEMA = "codex-complexity-classification-v1"
THRESHOLD = 4
COMPLEX_THRESHOLD = 8


class ComplexityError(ValueError):
    """Raised when structural evidence cannot be classified safely."""


def _count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ComplexityError(f"{name} must be a non-negative integer")
    return value


def _steps(entry_tier: str, terra_permit: bool) -> list[str]:
    if terra_permit:
        return ["implement", "validate", "self-review"]
    if entry_tier == "fast" and not terra_permit:
        return ["implement", "validate", "self-review"]
    if entry_tier == "standard":
        return ["plan", "implement", "validate", "self-review"]
    return ["plan", "plan-review", "implement", "validate", "judge"]


def classify(
    A: Any,
    B: Any,
    U: Any,
    *,
    preflight_complete: bool = False,
    evidence_truncated: bool = False,
    sol_pin: bool = False,
    terra_permit: bool = False,
) -> dict[str, Any]:
    """Return the fail-closed complexity contract for bounded structural evidence."""
    a, b, u = _count(A, "A"), _count(B, "B"), _count(U, "U")
    if not isinstance(preflight_complete, bool) or not isinstance(evidence_truncated, bool):
        raise ComplexityError("preflight_complete and evidence_truncated must be booleans")
    if not isinstance(sol_pin, bool) or not isinstance(terra_permit, bool):
        raise ComplexityError("sol_pin and terra_permit must be booleans")

    score = math.log2(1 + a) + b + 2 * u
    raw_tier = "fast" if score < THRESHOLD else "reviewed"
    raw_entry_tier = (
        "fast"
        if score < THRESHOLD
        else "standard" if score < COMPLEX_THRESHOLD else "complex"
    )
    incomplete = not preflight_complete or evidence_truncated
    effective_tier = "reviewed" if incomplete or sol_pin or terra_permit else raw_tier
    entry_tier = (
        "complex"
        if incomplete or sol_pin
        else "standard" if terra_permit else raw_entry_tier
    )
    implementation_role = None if incomplete else ("economy" if effective_tier == "fast" else "balanced")
    entry_role = (
        "quality_first"
        if entry_tier == "complex"
        else "balanced" if entry_tier == "standard" else "economy"
    )
    result: dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "status": "incomplete" if incomplete else "classified",
        "score": score,
        "structural_tier": raw_tier,
        "effective_tier": effective_tier,
        "entry_tier": entry_tier,
        "entry_role": entry_role,
        "implementation_role": implementation_role,
        "required_steps": ["complete-preflight"] if incomplete else _steps(
            entry_tier, terra_permit and not sol_pin
        ),
    }
    if incomplete:
        result["reason"] = "preflight evidence is incomplete or truncated"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--A", type=int, required=True, dest="a")
    parser.add_argument("--B", type=int, required=True, dest="b")
    parser.add_argument("--U", type=int, required=True, dest="u")
    parser.add_argument("--preflight-complete", action="store_true")
    parser.add_argument("--evidence-truncated", action="store_true")
    parser.add_argument("--sol-pin", action="store_true")
    parser.add_argument("--terra-permit", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = classify(
            args.a, args.b, args.u, preflight_complete=args.preflight_complete,
            evidence_truncated=args.evidence_truncated, sol_pin=args.sol_pin,
            terra_permit=args.terra_permit,
        )
    except ComplexityError as exc:
        print(json.dumps({"schema": OUTPUT_SCHEMA, "status": "invalid", "error": str(exc)}))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0 if output["status"] == "classified" else 3


if __name__ == "__main__":
    sys.exit(main())
