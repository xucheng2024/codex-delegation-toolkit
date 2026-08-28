#!/usr/bin/env python3
"""Ask Sol for a task graph, validate it, and repair its schema once in-session."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from schedule_task_graph import TaskGraphError, schedule


OUTPUT_SCHEMA = "codex-sol-decomposition-receipt-v1"
DEFAULT_MODEL = "gpt-5.6-sol"


class DecompositionError(ValueError):
    """Raised when a Sol task graph cannot safely enter the scheduler."""


Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]


def _run(command: Sequence[str], input_text: str | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, input=input_text, text=True, capture_output=True, check=False)


def _detail(result: subprocess.CompletedProcess[str]) -> str:
    detail = result.stderr.strip() or result.stdout.strip() or "codex invocation failed"
    return detail if len(detail) <= 2000 else detail[:1000] + "\n... output truncated ...\n" + detail[-900:]


def extract_started_thread(jsonl: str) -> str:
    """Return the one thread created by this invocation's JSON event stream."""
    thread_ids: list[str] = []
    for line in jsonl.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            thread_ids.append(event["thread_id"])
    if len(thread_ids) != 1:
        raise DecompositionError("Sol launch did not emit exactly one thread.started event")
    return thread_ids[0]


def _read_validated_graph(path: Path) -> dict[str, Any]:
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
        schedule(graph)
    except (OSError, UnicodeError, json.JSONDecodeError, TaskGraphError) as exc:
        raise DecompositionError(str(exc)) from exc
    return graph


def _repair_prompt(error: str) -> str:
    return (
        "Your previous task graph is semantically accepted but failed the strict JSON schema. "
        "Return ONLY a complete replacement JSON object for codex-task-graph-v1; do not explain, "
        "do not change the decomposition unless needed for schema validity. Each task.acceptance and "
        "task.validation must be one non-empty string (not arrays). integration_validation must be a "
        "non-empty array of non-empty strings. Every task must contain exactly id, objective, owned_paths, "
        "depends_on, acceptance, validation, A, B, U, preflight_complete, and evidence_truncated; use no "
        "unknown fields. "
        f"Validator error: {error}"
    )


def decompose(
    prompt: str, *, output: Path, codex_bin: str = "codex", model: str = DEFAULT_MODEL,
    runner: Runner = _run,
) -> dict[str, Any]:
    """Create one Sol thread and allow at most one schema-only same-thread repair."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise DecompositionError("prompt must be a non-empty string")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="codex-sol-decompose-", dir=output.parent) as directory:
        initial = Path(directory) / "initial.json"
        first = runner(
            [codex_bin, "exec", "--json", "-m", model, "-s", "read-only", "-o", str(initial), "-"],
            prompt,
        )
        if first.returncode:
            raise DecompositionError(_detail(first))
        thread_id = extract_started_thread(first.stdout)
        try:
            graph = _read_validated_graph(initial)
            repaired = False
        except DecompositionError as initial_error:
            corrected = Path(directory) / "corrected.json"
            retry = runner(
                [codex_bin, "exec", "resume", "--json", thread_id, "-o", str(corrected), _repair_prompt(str(initial_error))],
                None,
            )
            if retry.returncode:
                raise DecompositionError(f"same-thread schema repair failed: {_detail(retry)}")
            graph = _read_validated_graph(corrected)
            repaired = True
        output.write_text(json.dumps(graph, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "accepted",
        "schema_repair_used": repaired,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    prompt = parser.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt")
    prompt.add_argument("--prompt-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)
    try:
        source = args.prompt if args.prompt is not None else args.prompt_file.read_text(encoding="utf-8")
        result = decompose(source, output=args.output, codex_bin=args.codex_bin, model=args.model)
    except (OSError, UnicodeError, DecompositionError) as exc:
        print(json.dumps({"schema": OUTPUT_SCHEMA, "status": "incomplete", "error": str(exc)}, sort_keys=True))
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
