#!/usr/bin/env python3
"""Execute an approved parallel-leased task graph in isolated Git worktrees.

This is deliberately an opt-in executor. It accepts the output of
``orchestrate_workflow.py dispatch`` with ``dispatch_mode=parallel-leased``.
Workers never write the caller's checkout: each wave starts from an integration
worktree, then the executor validates and commits its patches there. Only after
all waves and integration validation succeed is the combined diff applied to
the originally clean checkout.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from resource_leases import acquire, release


INPUT_SCHEMA = "codex-workflow-queue-decision-v1"
OUTPUT_SCHEMA = "codex-parallel-execution-v1"


class ExecutionError(ValueError):
    """Raised before the executor can safely change a repository."""


def _run(command: list[str], cwd: Path, *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, input=input_text, text=True, capture_output=True, check=False)


def _git(repo: Path, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    result = _run(["git", *args], repo, input_text=input_text)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise ExecutionError(detail)
    return result


def _clean(repo: Path) -> None:
    if _git(repo, "status", "--porcelain").stdout.strip():
        raise ExecutionError("parallel execution requires a clean repository checkout")


def _path_owned(path: str, owned_paths: list[str]) -> bool:
    return any(path == owned or path.startswith(owned + "/") for owned in owned_paths)


def _task_prompt(task: dict[str, Any]) -> str:
    packet = {
        "schema": "codex-parallel-task-v1",
        "id": task["id"],
        "objective": task["objective"],
        "owned_paths": task["owned_paths"],
        "acceptance": task["acceptance"],
        "validation": task["validation"],
    }
    return (
        "Implement exactly this owned task in the current isolated worktree. "
        "Do not edit paths outside owned_paths. Run the declared validation. Do not commit.\n"
        + json.dumps(packet, sort_keys=True, separators=(",", ":"))
    )


def _detail(result: subprocess.CompletedProcess[str]) -> str:
    text = result.stderr.strip() or result.stdout.strip()
    return text if len(text) <= 2000 else text[:1000] + "\n... output truncated ...\n" + text[-900:]


def _validate_decision(value: Any) -> tuple[dict[str, Any], int]:
    if not isinstance(value, dict) or value.get("schema") != INPUT_SCHEMA:
        raise ExecutionError(f"input schema must be {INPUT_SCHEMA}")
    if value.get("status") != "queued" or value.get("dispatch_mode") != "parallel-leased":
        raise ExecutionError("input must be a queued parallel-leased graph dispatch")
    maximum = value.get("max_parallelism")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 2:
        raise ExecutionError("parallel dispatch requires max_parallelism of at least two")
    schedule = value.get("schedule")
    if not isinstance(schedule, dict) or not isinstance(schedule.get("waves"), list):
        raise ExecutionError("parallel dispatch is missing schedule waves")
    for wave in schedule["waves"]:
        if not isinstance(wave, list):
            raise ExecutionError("schedule wave must be a list")
        for task in wave:
            required = {"id", "owned_paths", "lease_resources", "model", "effort", "work_type", "objective", "acceptance", "validation"}
            if not isinstance(task, dict) or not required <= set(task):
                raise ExecutionError("scheduled task is missing execution fields")
            if task["work_type"] != "implement":
                raise ExecutionError("parallel executor accepts only decomposed implementation leaves")
            if not isinstance(task["owned_paths"], list) or not task["owned_paths"]:
                raise ExecutionError("scheduled task owned_paths must be non-empty")
    return schedule, maximum


def _worker(task: dict[str, Any], worktree: Path, codex_bin: str) -> dict[str, Any]:
    command = [
        codex_bin, "exec", "-m", task["model"], "-c",
        f'model_reasoning_effort="{task["effort"]}"', "--sandbox", "workspace-write", "-",
    ]
    model = _run(command, worktree, input_text=_task_prompt(task))
    if model.returncode:
        return {"id": task["id"], "status": "failed", "stage": "model", "detail": _detail(model)}
    validation = _run(["sh", "-lc", task["validation"]], worktree)
    if validation.returncode:
        return {"id": task["id"], "status": "failed", "stage": "validation", "detail": _detail(validation)}
    _git(worktree, "add", "-N", ".")
    changed = [line for line in _git(worktree, "diff", "--name-only", "HEAD").stdout.splitlines() if line]
    if any(not _path_owned(path, task["owned_paths"]) for path in changed):
        return {"id": task["id"], "status": "failed", "stage": "ownership", "detail": ",".join(changed)}
    check = _git(worktree, "diff", "--check", "HEAD")
    patch = _git(worktree, "diff", "--binary", "HEAD").stdout
    return {"id": task["id"], "status": "passed", "changed_paths": changed, "patch": patch, "check": check.stdout}


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    """Keep potentially large patches and command output out of the control-plane result."""
    return {key: value for key, value in result.items() if key not in {"patch", "check"}}


def execute(value: Any, *, repo: Path, lease_state: Path, worktree_root: Path, codex_bin: str = "codex", lease_ttl_seconds: int = 1800) -> dict[str, Any]:
    schedule, maximum = _validate_decision(value)
    repo = repo.resolve()
    _clean(repo)
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    worktree_root.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="codex-parallel-", dir=worktree_root))
    integration = scratch / "integration"
    workers: list[Path] = []
    results: list[dict[str, Any]] = []
    try:
        _git(repo, "worktree", "add", "--detach", str(integration), base)
        for index, wave in enumerate(schedule["waves"]):
            acquired: list[dict[str, Any]] = []
            for task in wave:
                lease = acquire(lease_state, task["id"], task["lease_resources"], lease_ttl_seconds)
                if lease["status"] != "acquired":
                    for held in acquired:
                        release(lease_state, held["id"])
                    return {"schema": OUTPUT_SCHEMA, "status": "waiting", "wave": index, "lease": lease, "results": results}
                acquired.append(task)
            wave_results: list[dict[str, Any]] = []
            try:
                for task in acquired:
                    worktree = scratch / f"wave-{index}-{task['id']}"
                    _git(repo, "worktree", "add", "--detach", str(worktree), "HEAD")
                    # The worker must see the integration result from prior waves.
                    _git(worktree, "reset", "--hard", _git(integration, "rev-parse", "HEAD").stdout.strip())
                    workers.append(worktree)
                with concurrent.futures.ThreadPoolExecutor(max_workers=maximum) as pool:
                    futures = [pool.submit(_worker, task, workers[-len(acquired) + position], codex_bin) for position, task in enumerate(acquired)]
                    wave_results = [future.result() for future in futures]
                results.extend(_public_result(result) for result in wave_results)
                failures = [result for result in wave_results if result["status"] != "passed"]
                if failures:
                    return {"schema": OUTPUT_SCHEMA, "status": "failed", "wave": index, "results": results}
                for result in sorted(wave_results, key=lambda item: item["id"]):
                    if result["patch"]:
                        _git(integration, "apply", "--whitespace=nowarn", "-", input_text=result["patch"])
                if any(result["patch"] for result in wave_results):
                    _git(integration, "add", "-A")
                    _git(integration, "-c", "user.name=Codex Parallel", "-c", "user.email=codex@localhost", "commit", "-m", f"parallel wave {index}")
            finally:
                for task in acquired:
                    release(lease_state, task["id"])
                for worktree in workers:
                    _git(repo, "worktree", "remove", "--force", str(worktree))
                workers.clear()
        for command in schedule.get("integration_validation", []):
            validation = _run(["sh", "-lc", command], integration)
            if validation.returncode:
                return {"schema": OUTPUT_SCHEMA, "status": "failed", "stage": "integration-validation", "detail": _detail(validation), "results": results}
        patch = _git(integration, "diff", "--binary", f"{base}..HEAD").stdout
        if patch:
            _git(repo, "apply", "--whitespace=nowarn", "-", input_text=patch)
        return {"schema": OUTPUT_SCHEMA, "status": "completed", "results": results}
    finally:
        if integration.exists():
            _git(repo, "worktree", "remove", "--force", str(integration))
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--lease-state", type=Path, required=True)
    parser.add_argument("--worktree-root", type=Path, required=True)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--lease-ttl-seconds", type=int, default=1800)
    args = parser.parse_args(argv)
    try:
        value = json.loads(args.input.read_text(encoding="utf-8"))
        output = execute(value, repo=args.repo, lease_state=args.lease_state, worktree_root=args.worktree_root, codex_bin=args.codex_bin, lease_ttl_seconds=args.lease_ttl_seconds)
    except (OSError, UnicodeError, json.JSONDecodeError, ExecutionError, ValueError) as exc:
        print(json.dumps({"schema": OUTPUT_SCHEMA, "status": "invalid", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(output, sort_keys=True, allow_nan=False))
    return 0 if output["status"] == "completed" else 3


if __name__ == "__main__":
    sys.exit(main())
