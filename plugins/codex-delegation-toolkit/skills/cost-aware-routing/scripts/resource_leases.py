#!/usr/bin/env python3
"""Acquire, renew, release, and inspect atomic task resource leases.

The scheduler remains deterministic and does not execute agents itself. A host
uses this module immediately before starting a parallel worker, then gives that
worker an isolated worktree. A lease is a safety gate, not a substitute for
per-task validation or final integration validation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


STATE_SCHEMA = "codex-resource-leases-v1"


class LeaseError(ValueError):
    """Raised when a lease request is not a strict safe contract."""


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(char.isspace() for char in value):
        raise LeaseError(f"{name} must be a non-empty whitespace-free string")
    return value


def _positive(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LeaseError(f"{name} must be a positive integer")
    return value


def _path_resource(value: str) -> str:
    if not value.startswith("path:"):
        return value
    path = value.removeprefix("path:")
    if not path or path.startswith("/") or "\\" in path:
        raise LeaseError("path resource must be repository-relative POSIX")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise LeaseError("path resource contains an invalid component")
    return value


def normalize_resources(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise LeaseError("resources must be a non-empty list")
    resources = [_path_resource(_string(item, "resource")) for item in value]
    if len(resources) != len(set(resources)):
        raise LeaseError("resources must not contain duplicates")
    return sorted(resources)


def _paths_conflict(left: str, right: str) -> bool:
    if not left.startswith("path:") or not right.startswith("path:"):
        return left == right
    left_path, right_path = left.removeprefix("path:"), right.removeprefix("path:")
    return (
        left_path == right_path
        or left_path.startswith(right_path + "/")
        or right_path.startswith(left_path + "/")
    )


def _load(handle: Any) -> dict[str, Any]:
    handle.seek(0)
    content = handle.read()
    if not content:
        return {"schema": STATE_SCHEMA, "leases": []}
    try:
        state = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LeaseError("lease state is not valid JSON") from exc
    if not isinstance(state, dict) or set(state) != {"schema", "leases"} or state["schema"] != STATE_SCHEMA:
        raise LeaseError("lease state has an invalid schema")
    if not isinstance(state["leases"], list):
        raise LeaseError("lease state leases must be a list")
    return state


def _write(handle: Any, state: dict[str, Any]) -> None:
    handle.seek(0)
    handle.truncate()
    json.dump(state, handle, sort_keys=True, separators=(",", ":"))
    handle.flush()
    os.fsync(handle.fileno())


@contextmanager
def _exclusive_state(path: Path) -> Iterator[Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            import fcntl  # POSIX is the supported Codex host contract.
        except ImportError as exc:  # pragma: no cover - defensive for unsupported hosts.
            raise LeaseError("resource leases require POSIX file locking") from exc
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield handle
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _active(state: dict[str, Any], now: float) -> list[dict[str, Any]]:
    leases: list[dict[str, Any]] = []
    for lease in state["leases"]:
        if not isinstance(lease, dict) or set(lease) != {"task_id", "resources", "expires_at"}:
            raise LeaseError("lease state contains an invalid lease")
        task_id = _string(lease["task_id"], "lease task_id")
        resources = normalize_resources(lease["resources"])
        expires_at = lease["expires_at"]
        if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
            raise LeaseError("lease expires_at must be numeric")
        if expires_at > now:
            leases.append({"task_id": task_id, "resources": resources, "expires_at": expires_at})
    return leases


def acquire(state_path: Path, task_id: Any, resources: Any, ttl_seconds: Any, *, now: float | None = None) -> dict[str, Any]:
    task = _string(task_id, "task_id")
    requested = normalize_resources(resources)
    ttl = _positive(ttl_seconds, "ttl_seconds")
    current_time = time.time() if now is None else now
    with _exclusive_state(state_path) as handle:
        state = _load(handle)
        active = _active(state, current_time)
        retained = [lease for lease in active if lease["task_id"] != task]
        blockers = sorted({
            lease["task_id"]
            for lease in retained
            if any(_paths_conflict(resource, held) for resource in requested for held in lease["resources"])
        })
        if blockers:
            state["leases"] = active
            _write(handle, state)
            return {"schema": STATE_SCHEMA, "status": "waiting", "task_id": task, "blockers": blockers}
        lease = {"task_id": task, "resources": requested, "expires_at": current_time + ttl}
        state["leases"] = [*retained, lease]
        _write(handle, state)
        return {"schema": STATE_SCHEMA, "status": "acquired", **lease}


def release(state_path: Path, task_id: Any, *, now: float | None = None) -> dict[str, Any]:
    task = _string(task_id, "task_id")
    current_time = time.time() if now is None else now
    with _exclusive_state(state_path) as handle:
        state = _load(handle)
        active = _active(state, current_time)
        remaining = [lease for lease in active if lease["task_id"] != task]
        released = len(active) != len(remaining)
        state["leases"] = remaining
        _write(handle, state)
        return {"schema": STATE_SCHEMA, "status": "released" if released else "missing", "task_id": task}


def inspect(state_path: Path, *, now: float | None = None) -> dict[str, Any]:
    current_time = time.time() if now is None else now
    with _exclusive_state(state_path) as handle:
        state = _load(handle)
        active = _active(state, current_time)
        state["leases"] = active
        _write(handle, state)
        return {"schema": STATE_SCHEMA, "status": "ok", "leases": active}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    acquire_parser = subparsers.add_parser("acquire")
    acquire_parser.add_argument("--task", required=True)
    acquire_parser.add_argument("--resource", action="append", dest="resources", required=True)
    acquire_parser.add_argument("--ttl-seconds", type=int, required=True)
    release_parser = subparsers.add_parser("release")
    release_parser.add_argument("--task", required=True)
    subparsers.add_parser("inspect")
    args = parser.parse_args(argv)
    try:
        if args.command == "acquire":
            output = acquire(args.state, args.task, args.resources, args.ttl_seconds)
        elif args.command == "release":
            output = release(args.state, args.task)
        else:
            output = inspect(args.state)
    except (OSError, LeaseError) as exc:
        print(json.dumps({"schema": STATE_SCHEMA, "status": "invalid", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(output, sort_keys=True, allow_nan=False))
    return 0 if output["status"] != "waiting" else 3


if __name__ == "__main__":
    sys.exit(main())
