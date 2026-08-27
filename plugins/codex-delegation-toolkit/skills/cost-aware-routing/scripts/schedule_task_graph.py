#!/usr/bin/env python3
"""Validate and deterministically schedule a bounded task dependency graph."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_CLASSIFIER_SPEC = importlib.util.spec_from_file_location(
    "classify_complexity", Path(__file__).with_name("classify_complexity.py")
)
if _CLASSIFIER_SPEC is None or _CLASSIFIER_SPEC.loader is None:  # pragma: no cover - fixed sibling
    raise RuntimeError("unable to load classify_complexity.py")
_CLASSIFIER = importlib.util.module_from_spec(_CLASSIFIER_SPEC)
_CLASSIFIER_SPEC.loader.exec_module(_CLASSIFIER)
ComplexityError = _CLASSIFIER.ComplexityError
classify = _CLASSIFIER.classify


INPUT_SCHEMA = "codex-task-graph-v1"
OUTPUT_SCHEMA = "codex-task-graph-schedule-v1"
QUEUES = ("fast", "standard", "complex")
TASK_FIELDS = (
    "id", "objective", "owned_paths", "depends_on", "acceptance", "validation",
    "A", "B", "U", "preflight_complete", "evidence_truncated",
)


class TaskGraphError(ValueError):
    """Raised when a task graph cannot be safely scheduled."""


def _nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskGraphError(f"{name} must be a non-empty string")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TaskGraphError(f"{name} must be a non-negative integer")
    return value


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise TaskGraphError(f"{name} must be a boolean")
    return value


def normalize_path(value: Any) -> str:
    """Return a repository-relative POSIX path, rejecting ambiguous components."""
    path = _nonempty_string(value, "owned_paths entry")
    if path.startswith("/") or "\\" in path:
        raise TaskGraphError("owned paths must be repository-relative POSIX paths")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise TaskGraphError("owned path components must not be empty, dot, or dot-dot")
    return "/".join(parts)


def _conflicts(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _validate_task(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TaskGraphError("each task must be an object")
    missing = [field for field in TASK_FIELDS if field not in value]
    if missing:
        raise TaskGraphError(f"task missing required fields: {', '.join(missing)}")
    unknown = set(value) - set(TASK_FIELDS) - {"sol_pin", "terra_permit"}
    if unknown:
        raise TaskGraphError(f"task contains unknown fields: {', '.join(sorted(unknown))}")

    task = dict(value)
    task["id"] = _nonempty_string(task["id"], "task id")
    task["objective"] = _nonempty_string(task["objective"], "objective")
    task["acceptance"] = _nonempty_string(task["acceptance"], "acceptance")
    task["validation"] = _nonempty_string(task["validation"], "validation")
    if not isinstance(task["owned_paths"], list):
        raise TaskGraphError("owned_paths must be a list")
    task["owned_paths"] = [normalize_path(path) for path in task["owned_paths"]]
    if len(task["owned_paths"]) != len(set(task["owned_paths"])):
        raise TaskGraphError("owned_paths must not contain duplicates")
    if not isinstance(task["depends_on"], list) or not all(isinstance(dep, str) and dep for dep in task["depends_on"]):
        raise TaskGraphError("depends_on must be a list of non-empty strings")
    if len(task["depends_on"]) != len(set(task["depends_on"])):
        raise TaskGraphError("depends_on must not contain duplicates")
    for field in ("A", "B", "U"):
        task[field] = _nonnegative_int(task[field], field)
    for field in ("preflight_complete", "evidence_truncated"):
        task[field] = _boolean(task[field], field)
    for field in ("sol_pin", "terra_permit"):
        if field in task:
            task[field] = _boolean(task[field], field)
    return task


def validate_graph(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate graph structure and return normalized tasks and integration checks."""
    if not isinstance(value, dict) or set(value) != {"schema", "tasks", "integration_validation"}:
        raise TaskGraphError("graph must contain only schema, tasks, and integration_validation")
    if value["schema"] != INPUT_SCHEMA:
        raise TaskGraphError(f"schema must be {INPUT_SCHEMA}")
    if not isinstance(value["tasks"], list) or not value["tasks"]:
        raise TaskGraphError("tasks must be a non-empty list")
    if not isinstance(value["integration_validation"], list) or not value["integration_validation"]:
        raise TaskGraphError("integration_validation must be a non-empty list")
    integration = [_nonempty_string(item, "integration_validation entry") for item in value["integration_validation"]]
    tasks = [_validate_task(item) for item in value["tasks"]]
    ids = [task["id"] for task in tasks]
    if len(ids) != len(set(ids)):
        raise TaskGraphError("task ids must be unique")
    known = set(ids)
    for task in tasks:
        for dependency in task["depends_on"]:
            if dependency == task["id"]:
                raise TaskGraphError(f"task {task['id']} cannot depend on itself")
            if dependency not in known:
                raise TaskGraphError(f"task {task['id']} depends on unknown task {dependency}")
    return tasks, integration


def schedule(
    graph: Any, *, allow_recursive_delegation: bool = False,
    current_delegation_depth: int = 0, max_delegation_depth: int = 2,
) -> dict[str, Any]:
    """Return sorted Kahn waves with maximal greedy non-conflicting concurrency."""
    current = _nonnegative_int(current_delegation_depth, "current_delegation_depth")
    maximum = _nonnegative_int(max_delegation_depth, "max_delegation_depth")
    if current > maximum:
        raise TaskGraphError("current_delegation_depth must not exceed max_delegation_depth")
    if not isinstance(allow_recursive_delegation, bool):
        raise TaskGraphError("allow_recursive_delegation must be a boolean")
    tasks, integration = validate_graph(graph)
    by_id = {task["id"]: task for task in tasks}
    remaining = {task["id"]: set(task["depends_on"]) for task in tasks}
    dependents = {task["id"]: [] for task in tasks}
    for task in tasks:
        for dependency in task["depends_on"]:
            dependents[dependency].append(task["id"])
    ready = sorted(task_id for task_id, dependencies in remaining.items() if not dependencies)
    waves: list[list[dict[str, Any]]] = []
    completed: set[str] = set()
    may_delegate = allow_recursive_delegation and current < maximum
    while ready:
        selected: list[str] = []
        for task_id in ready:
            task = by_id[task_id]
            if not any(
                _conflicts(path, chosen_path)
                for chosen in selected
                for path in task["owned_paths"]
                for chosen_path in by_id[chosen]["owned_paths"]
            ):
                selected.append(task_id)
        if not selected:  # Defensive: a valid empty-scope graph always selects one.
            raise TaskGraphError("no non-conflicting ready task could be selected")
        wave: list[dict[str, Any]] = []
        for task_id in selected:
            task = dict(by_id[task_id])
            try:
                classification = classify(
                    task["A"], task["B"], task["U"],
                    preflight_complete=task["preflight_complete"],
                    evidence_truncated=task["evidence_truncated"],
                    sol_pin=task.get("sol_pin", False), terra_permit=task.get("terra_permit", False),
                )
            except ComplexityError as exc:
                raise TaskGraphError(f"task {task_id} cannot be classified: {exc}") from exc
            if classification["status"] != "classified":
                raise TaskGraphError(f"task {task_id} has incomplete or truncated preflight evidence")
            task["classification"] = classification
            task["queue"] = classification["entry_tier"]
            task["work_type"] = (
                "decompose" if classification["entry_tier"] == "complex" else "implement"
            )
            task["may_delegate"] = may_delegate
            if may_delegate:
                task["next_delegation_depth"] = current + 1
            wave.append(task)
        waves.append(wave)
        completed.update(selected)
        next_ready = set(ready) - set(selected)
        for task_id in selected:
            for dependent in dependents[task_id]:
                remaining[dependent].discard(task_id)
                if not remaining[dependent] and dependent not in completed:
                    next_ready.add(dependent)
        ready = sorted(next_ready)
    if len(completed) != len(tasks):
        raise TaskGraphError("task dependency graph contains a cycle")
    queues = {name: [] for name in QUEUES}
    for wave in waves:
        for task in wave:
            queues[task["queue"]].append(task["id"])
    owners: dict[str, list[dict[str, Any]]] = {name: [] for name in QUEUES}
    for wave in waves:
        for task in wave:
            queue = task["queue"]
            if not owners[queue]:
                owners[queue].append({"id": f"{queue}-1", "task_ids": []})
            owner = owners[queue][0]
            task["owner"] = owner["id"]
            owner["task_ids"].append(task["id"])
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "scheduled",
        "waves": waves,
        "queues": queues,
        "owners": owners,
        "integration_validation": integration,
        "final_steps": ["integration_validation", "judge"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--allow-recursive-delegation", action="store_true")
    parser.add_argument("--current-delegation-depth", type=int, default=0)
    parser.add_argument("--max-delegation-depth", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        graph = json.loads(args.input.read_text(encoding="utf-8"))
        output = schedule(
            graph,
            allow_recursive_delegation=args.allow_recursive_delegation,
            current_delegation_depth=args.current_delegation_depth,
            max_delegation_depth=args.max_delegation_depth,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TaskGraphError) as exc:
        print(json.dumps({"schema": OUTPUT_SCHEMA, "status": "invalid", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
