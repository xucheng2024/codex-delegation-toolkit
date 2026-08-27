#!/usr/bin/env python3
"""Reduce bounded workflow plans into deterministic routing and split decisions."""

from __future__ import annotations

import argparse
import json
import math
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


PLAN_INPUT_SCHEMA = "codex-workflow-plan-v1"
PLAN_OUTPUT_SCHEMA = "codex-workflow-plan-decision-v1"
VERIFY_INPUT_SCHEMA = "codex-workflow-verification-v1"
TRANSITION_OUTPUT_SCHEMA = "codex-workflow-transition-v1"
_COMPLEXITY_FIELDS = (
    "A", "B", "U", "preflight_complete", "evidence_truncated", "sol_pin", "terra_permit",
)
_PLAN_REQUIRED = {
    "schema", "parent", "available", "complexity", "allow_recursive_delegation",
    "current_delegation_depth", "max_delegation_depth",
}
_PLAN_OPTIONAL = {"graph", "economics", "delegation_available"}
_ECONOMICS_FIELDS = {"latency_weight", "minimum_gain_ratio", "single", "dag"}
_SINGLE_FIELDS = {"cost_units", "latency_ms", "success_probability"}
_DAG_FIELDS = {"overhead_cost_units", "overhead_latency_ms", "success_probability", "tasks"}


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


def _finite(value: Any, name: str, *, positive: bool = False) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkflowError(f"{name} must be finite")
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise WorkflowError(f"{name} must be finite") from exc
    if not finite:
        raise WorkflowError(f"{name} must be finite")
    if value < 0 or (positive and value <= 0):
        comparator = "positive" if positive else "non-negative"
        raise WorkflowError(f"{name} must be {comparator}")
    return value


def _finite_result(value: Any, name: str) -> float | int:
    """Fail closed when arithmetic produces a non-finite or unrepresentable result."""
    return _finite(value, name)


def _sum_finite(values: Any, name: str) -> float | int:
    try:
        return _finite_result(sum(values), name)
    except OverflowError as exc:
        raise WorkflowError(f"{name} must be finite") from exc


def _exact_object(value: Any, fields: set[str] | tuple[str, ...], name: str) -> dict[str, Any]:
    expected = set(fields)
    if not isinstance(value, dict) or set(value) != expected:
        raise WorkflowError(f"{name} must contain only {', '.join(sorted(expected))}")
    return value


def _validate_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not _PLAN_REQUIRED <= set(value) or set(value) - (_PLAN_REQUIRED | _PLAN_OPTIONAL):
        raise WorkflowError("plan contains missing or unknown fields")
    if value["schema"] != PLAN_INPUT_SCHEMA:
        raise WorkflowError(f"schema must be {PLAN_INPUT_SCHEMA}")
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
    for field in _PLAN_OPTIONAL:
        if field in value:
            normalized[field] = value[field]
    if "economics" in normalized and "graph" not in normalized:
        raise WorkflowError("economics requires graph")
    return normalized


def _score(cost: float | int, latency: float | int, probability: float | int, weight: float | int, name: str) -> float | int:
    try:
        weighted_latency = _finite_result(weight * latency, f"{name} weighted latency")
        numerator = _finite_result(cost + weighted_latency, f"{name} numerator")
        return _finite_result(numerator / probability, name)
    except OverflowError as exc:
        raise WorkflowError(f"{name} must be finite") from exc


def _evaluate_economics(value: Any, scheduled_ids: set[str]) -> dict[str, Any]:
    economics = _exact_object(value, _ECONOMICS_FIELDS, "economics")
    weight = _finite(economics["latency_weight"], "economics.latency_weight")
    gain_floor = _finite(economics["minimum_gain_ratio"], "economics.minimum_gain_ratio")
    if gain_floor >= 1:
        raise WorkflowError("economics.minimum_gain_ratio must be less than 1")
    single = _exact_object(economics["single"], _SINGLE_FIELDS, "economics.single")
    dag = _exact_object(economics["dag"], _DAG_FIELDS, "economics.dag")
    single_cost = _finite(single["cost_units"], "economics.single.cost_units")
    single_latency = _finite(single["latency_ms"], "economics.single.latency_ms")
    single_probability = _finite(single["success_probability"], "economics.single.success_probability", positive=True)
    if single_probability > 1:
        raise WorkflowError("economics.single.success_probability must be at most 1")
    overhead_cost = _finite(dag["overhead_cost_units"], "economics.dag.overhead_cost_units")
    overhead_latency = _finite(dag["overhead_latency_ms"], "economics.dag.overhead_latency_ms")
    dag_probability = _finite(dag["success_probability"], "economics.dag.success_probability", positive=True)
    if dag_probability > 1:
        raise WorkflowError("economics.dag.success_probability must be at most 1")
    tasks = dag["tasks"]
    if not isinstance(tasks, dict) or set(tasks) != scheduled_ids:
        raise WorkflowError("economics.dag.tasks task IDs must exactly match scheduled task IDs")
    costs: dict[str, float | int] = {}
    latencies: dict[str, float | int] = {}
    for task_id, estimate in tasks.items():
        _string(task_id, "economics.dag.tasks key")
        estimate = _exact_object(estimate, {"cost_units", "latency_ms"}, f"economics.dag.tasks.{task_id}")
        costs[task_id] = _finite(estimate["cost_units"], f"economics.dag.tasks.{task_id}.cost_units")
        latencies[task_id] = _finite(estimate["latency_ms"], f"economics.dag.tasks.{task_id}.latency_ms")
    return {
        "weight": weight, "gain_floor": gain_floor, "single": (single_cost, single_latency, single_probability),
        "dag": (overhead_cost, overhead_latency, dag_probability, costs, latencies),
    }


def decide_plan(value: Any, *, roles: dict[str, str] | None = None) -> dict[str, Any]:
    """Return the pure strict plan decision without invoking a model or persisting state."""
    plan = _validate_plan(value)
    complexity = plan["complexity"]
    try:
        classification = classify(**complexity)
    except ComplexityError as exc:
        raise WorkflowError(str(exc)) from exc
    if classification["status"] != "classified":
        return {
            "schema": PLAN_OUTPUT_SCHEMA, "status": "incomplete", "classification": classification,
            "split_decision": {
                "status": "not-evaluated", "selected": "single", "reason": "preflight incomplete",
            },
            "execution_mode": "single",
        }
    schedule_output: dict[str, Any] | None = None
    if "graph" in plan:
        try:
            schedule_output = schedule(
                plan["graph"], allow_recursive_delegation=plan["allow_recursive_delegation"],
                current_delegation_depth=plan["current_delegation_depth"],
                max_delegation_depth=plan["max_delegation_depth"],
            )
        except TaskGraphError as exc:
            raise WorkflowError(str(exc)) from exc
    if "economics" not in plan:
        split_decision: dict[str, Any] = {
            "status": "insufficient", "selected": "single", "reason": "economics unavailable",
        }
    else:
        assert schedule_output is not None
        scheduled_ids = {item["id"] for wave in schedule_output["waves"] for item in wave}
        parsed = _evaluate_economics(plan["economics"], scheduled_ids)
        single_cost, single_latency, single_probability = parsed["single"]
        overhead_cost, overhead_latency, dag_probability, costs, latencies = parsed["dag"]
        try:
            dag_cost = _finite_result(overhead_cost + _sum_finite(costs.values(), "dag leaf cost"), "dag cost")
            wave_latencies = [max(latencies[item["id"]] for item in wave) for wave in schedule_output["waves"]]
            dag_latency = _finite_result(
                overhead_latency + _sum_finite(wave_latencies, "dag wave latency"), "dag latency"
            )
        except OverflowError as exc:
            raise WorkflowError("dag economics must be finite") from exc
        single_score = _score(single_cost, single_latency, single_probability, parsed["weight"], "single score")
        dag_score = _score(dag_cost, dag_latency, dag_probability, parsed["weight"], "dag score")
        if single_score == 0:
            gain_ratio: float | int = 0
        else:
            try:
                gain_delta = _finite_result(single_score - dag_score, "gain delta")
                gain_ratio = _finite_result(gain_delta / single_score, "gain ratio")
            except OverflowError as exc:
                raise WorkflowError("gain ratio must be finite") from exc
        selected = "dag" if single_score != 0 and gain_ratio > 0 and gain_ratio >= parsed["gain_floor"] else "single"
        split_decision = {
            "status": "evaluated", "selected": selected, "single_score": single_score,
            "dag_score": dag_score, "gain_ratio": gain_ratio,
        }
    active_roles = roles if roles is not None else load_role_map(_SCRIPT_DIR.parent / "references" / "model-role-map.json")
    # Entry tier controls workflow shape. The legacy effective tier only
    # controls the implementation role. A supplied graph is already approved
    # by contract, so it must not trigger another planning pass.
    needs_plan = classification["entry_tier"] == "complex" and "graph" not in plan
    step = "plan" if needs_plan else "implement"
    try:
        next_action = route_decide(
            step, plan["parent"], complexity["sol_pin"], complexity["terra_permit"], set(plan["available"]),
            active_roles, complexity_tier=classification["effective_tier"],
            delegation_available=plan["delegation_available"],
        )
    except RouteError as exc:
        raise WorkflowError(str(exc)) from exc
    output: dict[str, Any] = {
        "schema": PLAN_OUTPUT_SCHEMA, "status": "planned", "classification": classification,
        "split_decision": split_decision, "execution_mode": split_decision["selected"], "next_action": next_action,
    }
    if schedule_output is not None:
        output["schedule"] = schedule_output
    return output


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
    for command in ("plan", "after-implement"):
        child = subparsers.add_parser(command)
        child.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    schema = PLAN_OUTPUT_SCHEMA if args.command == "plan" else TRANSITION_OUTPUT_SCHEMA
    try:
        value = json.loads(args.input.read_text(encoding="utf-8"))
        output = decide_plan(value) if args.command == "plan" else decide_after_implement(value)
    except (OSError, UnicodeError, json.JSONDecodeError, WorkflowError, RouteError) as exc:
        print(json.dumps({"schema": schema, "status": "invalid", "error": str(exc)}, sort_keys=True, allow_nan=False))
        return 2
    print(json.dumps(output, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
