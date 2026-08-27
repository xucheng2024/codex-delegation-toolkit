#!/usr/bin/env python3
"""Classify work into model queues and schedule approved task graphs."""

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
from escalate_step import decide as escalate_decide
from route_step import RouteError, decide as route_decide, load_role_map
from schedule_task_graph import TaskGraphError, schedule


QUEUE_INPUT_SCHEMA = "codex-workflow-queue-v1"
QUEUE_OUTPUT_SCHEMA = "codex-workflow-queue-decision-v1"
VERIFY_INPUT_SCHEMA = "codex-workflow-verification-v1"
TRANSITION_OUTPUT_SCHEMA = "codex-workflow-transition-v1"
_COMPLEXITY_FIELDS = (
    "A", "B", "U", "preflight_complete", "evidence_truncated", "sol_pin", "terra_permit",
)
_QUEUE_REQUIRED = {
    "schema", "parent", "available", "complexity", "allow_recursive_delegation",
    "current_delegation_depth", "max_delegation_depth",
}
_QUEUE_OPTIONAL = {"graph", "delegation_available"}


class WorkflowError(ValueError):
    """Raised when a workflow reducer input is not a safe strict contract."""


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f"{name} must be a non-empty string")
    return value


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise WorkflowError(f"{name} must be a boolean")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorkflowError(f"{name} must be a non-negative integer")
    return value


def _exact_object(value: Any, fields: set[str] | tuple[str, ...], name: str) -> dict[str, Any]:
    expected = set(fields)
    if not isinstance(value, dict) or set(value) != expected:
        raise WorkflowError(f"{name} must contain only {', '.join(sorted(expected))}")
    return value


def _validate_queue_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not _QUEUE_REQUIRED <= set(value) or set(value) - (_QUEUE_REQUIRED | _QUEUE_OPTIONAL):
        raise WorkflowError("queue request contains missing or unknown fields")
    if value["schema"] != QUEUE_INPUT_SCHEMA:
        raise WorkflowError(f"schema must be {QUEUE_INPUT_SCHEMA}")
    parent = _string(value["parent"], "parent")
    available = value["available"]
    if not isinstance(available, list) or not all(isinstance(item, str) and item.strip() for item in available):
        raise WorkflowError("available must be a list of non-empty strings")
    if len(available) != len(set(available)):
        raise WorkflowError("available must not contain duplicates")
    complexity = _exact_object(value["complexity"], _COMPLEXITY_FIELDS, "complexity")
    normalized_complexity = dict(complexity)
    for field in ("A", "B", "U"):
        normalized_complexity[field] = _nonnegative_int(complexity[field], f"complexity.{field}")
    for field in ("preflight_complete", "evidence_truncated", "sol_pin", "terra_permit"):
        normalized_complexity[field] = _boolean(complexity[field], f"complexity.{field}")
    current = _nonnegative_int(value["current_delegation_depth"], "current_delegation_depth")
    maximum = _nonnegative_int(value["max_delegation_depth"], "max_delegation_depth")
    if current > maximum:
        raise WorkflowError("current_delegation_depth must not exceed max_delegation_depth")
    normalized: dict[str, Any] = {
        "parent": parent, "available": available, "complexity": normalized_complexity,
        "allow_recursive_delegation": _boolean(value["allow_recursive_delegation"], "allow_recursive_delegation"),
        "current_delegation_depth": current, "max_delegation_depth": maximum,
        "delegation_available": _boolean(
            value.get("delegation_available", False), "delegation_available"
        ),
    }
    if "graph" in value:
        normalized["graph"] = value["graph"]
    return normalized


def _assign_workers(
    schedule_output: dict[str, Any], roles: dict[str, str], available: set[str]
) -> None:
    """Attach the configured queue worker to every scheduled task."""
    for wave in schedule_output["waves"]:
        for task in wave:
            role = task["classification"]["entry_role"]
            model = roles.get(role)
            if model is None:
                raise WorkflowError(f"{role} role is not configured")
            if model not in available:
                raise WorkflowError(f"model for {task['queue']} queue is unavailable")
            task["role"] = role
            task["model"] = model
            task["effort"] = "medium"
    for queue, owners in schedule_output["owners"].items():
        if not owners:
            continue
        role = {"fast": "economy", "standard": "balanced", "complex": "quality_first"}[queue]
        model = roles[role]
        for owner in owners:
            owner.update({"role": role, "model": model, "effort": "medium"})


def decide_queue(value: Any, *, roles: dict[str, str] | None = None) -> dict[str, Any]:
    """Return a deterministic queue decision without invoking a model."""
    request = _validate_queue_request(value)
    complexity = request["complexity"]
    try:
        classification = classify(**complexity)
    except ComplexityError as exc:
        raise WorkflowError(str(exc)) from exc
    if classification["status"] != "classified":
        return {
            "schema": QUEUE_OUTPUT_SCHEMA, "status": "incomplete", "classification": classification,
            "queue": "blocked",
            "execution_mode": "single",
        }
    active_roles = roles if roles is not None else load_role_map(
        _SCRIPT_DIR.parent / "references" / "model-role-map.json"
    )
    schedule_output: dict[str, Any] | None = None
    if "graph" in request:
        try:
            schedule_output = schedule(
                request["graph"], allow_recursive_delegation=request["allow_recursive_delegation"],
                current_delegation_depth=request["current_delegation_depth"],
                max_delegation_depth=request["max_delegation_depth"],
            )
        except TaskGraphError as exc:
            raise WorkflowError(str(exc)) from exc
        _assign_workers(schedule_output, active_roles, set(request["available"]))
        return {
            "schema": QUEUE_OUTPUT_SCHEMA,
            "status": "queued",
            "classification": classification,
            "queue": classification["queue"],
            "execution_mode": "waves",
            "dispatch_mode": "serial",
            "failure_policy": "stop-dependent-tasks",
            "schedule": schedule_output,
        }

    step = "decompose" if classification["queue"] == "complex" else "implement"
    try:
        next_action = route_decide(
            step, request["parent"], complexity["sol_pin"], complexity["terra_permit"], set(request["available"]),
            active_roles, complexity_tier=classification["effective_tier"],
            delegation_available=request["delegation_available"],
        )
    except RouteError as exc:
        raise WorkflowError(str(exc)) from exc
    return {
        "schema": QUEUE_OUTPUT_SCHEMA,
        "status": "queued",
        "classification": classification,
        "queue": classification["queue"],
        "execution_mode": "single",
        "next_action": next_action,
    }


def decide_after_implement(value: Any, *, roles: dict[str, str] | None = None) -> dict[str, Any]:
    """Strictly compose the existing post-verifier escalation contract."""
    required = {"schema", "parent", "available", "current_effort", "verifier"}
    optional = {"delegation_available"}
    if not isinstance(value, dict) or not required <= set(value) or set(value) - (required | optional):
        raise WorkflowError("verification contains missing or unknown fields")
    if value["schema"] != VERIFY_INPUT_SCHEMA:
        raise WorkflowError(f"schema must be {VERIFY_INPUT_SCHEMA}")
    parent = _string(value["parent"], "parent")
    available = value["available"]
    if not isinstance(available, list) or not all(isinstance(item, str) and item.strip() for item in available):
        raise WorkflowError("available must be a list of non-empty strings")
    if len(available) != len(set(available)):
        raise WorkflowError("available must not contain duplicates")
    current_effort = value["current_effort"]
    verifier = value["verifier"]
    delegation_available = _boolean(
        value.get("delegation_available", False), "delegation_available"
    )
    if current_effort not in ("medium", "high") or verifier not in ("pass", "fail", "incomplete"):
        raise WorkflowError("current_effort or verifier is invalid")
    active_roles = roles if roles is not None else load_role_map(_SCRIPT_DIR.parent / "references" / "model-role-map.json")
    try:
        next_action = escalate_decide(
            "implement",
            current_effort,
            verifier,
            parent,
            set(available),
            active_roles,
            delegation_available,
        )
    except RouteError as exc:
        raise WorkflowError(str(exc)) from exc
    return {"schema": TRANSITION_OUTPUT_SCHEMA, "status": "transitioned", "next_action": next_action}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("dispatch", "after-implement"):
        child = subparsers.add_parser(command)
        child.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    schema = QUEUE_OUTPUT_SCHEMA if args.command == "dispatch" else TRANSITION_OUTPUT_SCHEMA
    try:
        value = json.loads(args.input.read_text(encoding="utf-8"))
        output = decide_queue(value) if args.command == "dispatch" else decide_after_implement(value)
    except (OSError, UnicodeError, json.JSONDecodeError, WorkflowError, RouteError) as exc:
        print(json.dumps({"schema": schema, "status": "invalid", "error": str(exc)}, sort_keys=True, allow_nan=False))
        return 2
    print(json.dumps(output, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
