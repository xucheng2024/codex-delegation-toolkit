#!/usr/bin/env python3
"""Measure respawn+rebuild capsule vs same-child delta/resume on Codex 0.149."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.handoff_input_ab import (  # noqa: E402
    CASES,
    MODEL,
    EFFORT,
    cache_usage,
    load_renderer,
    treatment_packet,
)


OUT = ROOT / "experiments" / "same_child_delta_results" / time.strftime("%Y%m%dT%H%M%S")
FIRST = CASES[0]
FOLLOW = CASES[4]
PROFILE: str | None = None
ACTIVE_MODEL = MODEL
CODEX_HOME: Path | None = None


def delta_prompt(invariant: str, diff: str) -> str:
    return (
        "Also review this second diff against its invariant. "
        "Do not rebuild a handoff capsule.\n"
        f"INVARIANT: {invariant}\n"
        f"DIFF:\n{diff.strip()}\n"
    )


def rebuilt_prompt(renderer: Any, invariant: str, diff: str) -> str:
    return renderer.render_packet("review", treatment_packet(invariant, diff))


def cheap_ab() -> dict[str, Any]:
    renderer = load_renderer()
    rebuilt = rebuilt_prompt(renderer, FOLLOW[1], FOLLOW[2])
    delta = delta_prompt(FOLLOW[1], FOLLOW[2])
    rebuilt_bytes = len(rebuilt.encode("utf-8"))
    delta_bytes = len(delta.encode("utf-8"))
    return {
        "gate": "cheap",
        "pass": delta_bytes < rebuilt_bytes,
        "rebuilt_bytes": rebuilt_bytes,
        "delta_bytes": delta_bytes,
        "byte_ratio": round(delta_bytes / rebuilt_bytes, 4) if rebuilt_bytes else None,
    }


def _uncached(cache: dict[str, int | None]) -> int | None:
    input_tokens = cache.get("input_tokens")
    cached = cache.get("cached_tokens")
    if isinstance(input_tokens, int) and isinstance(cached, int):
        return input_tokens - cached
    return None


def _parse_events(stdout: str) -> tuple[str | None, dict[str, Any], str | None]:
    thread_id = None
    usage: dict[str, Any] = {}
    error = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
        if event.get("type") == "turn.completed":
            raw = event.get("usage", {})
            if isinstance(raw, dict):
                usage = raw
        if event.get("type") in {"error", "turn.failed"} and error is None:
            payload = event.get("error") if isinstance(event.get("error"), dict) else {}
            error = event.get("message") or payload.get("message")
    return thread_id, usage, error


def _run(command: list[str], prompt: str, directory: Path, label: str) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    answer = directory / "answer.md"
    if "--output-last-message" not in command:
        command.extend(["--output-last-message", str(answer)])
    env = dict(os.environ)
    if CODEX_HOME is not None:
        env["CODEX_HOME"] = str(CODEX_HOME)
    print(
        f"START {label} home={env.get('CODEX_HOME', '')!r} profile={PROFILE!r} "
        f"model={ACTIVE_MODEL} prompt_bytes={len(prompt.encode('utf-8'))} cmd={' '.join(command)}",
        flush=True,
    )
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, input=prompt, text=True, capture_output=True, timeout=1200, env=env)
    elapsed = round(time.monotonic() - started, 3)
    (directory / "events.jsonl").write_text(result.stdout, encoding="utf-8")
    (directory / "prompt.md").write_text(prompt, encoding="utf-8")
    if result.stderr:
        (directory / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    thread_id, usage, error = _parse_events(result.stdout)
    cache = cache_usage(usage)
    payload = {
        "label": label,
        "exit_code": result.returncode,
        "elapsed_seconds": elapsed,
        "thread_id": thread_id,
        "prompt_bytes": len(prompt.encode("utf-8")),
        "usage": usage,
        "cache": cache,
        "uncached_tokens": _uncached(cache),
        "error": error,
        "stderr_head": result.stderr[:800] if result.stderr else "",
    }
    print(f"DONE {label} {json.dumps(payload, ensure_ascii=False)}", flush=True)
    if result.returncode != 0:
        print(f"FAIL {label} exit={result.returncode} error={error!r} stderr={payload['stderr_head']!r}", flush=True)
    return payload


def _exec_cmd(extra: list[str]) -> list[str]:
    command = ["codex"]
    if PROFILE:
        command.extend(["-p", PROFILE])
    command.extend([
        "exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check",
        "--model", ACTIVE_MODEL, "-c", f'model_reasoning_effort="{EFFORT}"',
        *extra, "-",
    ])
    return command


def live_ab(out: Path | None = None) -> dict[str, Any]:
    renderer = load_renderer()
    directory = out or OUT
    first = rebuilt_prompt(renderer, FIRST[1], FIRST[2])
    control = rebuilt_prompt(renderer, FOLLOW[1], FOLLOW[2])
    treatment = delta_prompt(FOLLOW[1], FOLLOW[2])
    setup = _run(_exec_cmd([]), first, directory / "setup", "setup_full_capsule")
    thread_id = setup.get("thread_id")
    if setup["exit_code"] != 0 or not thread_id:
        return {"gate": "live", "pass": False, "error": "setup failed", "setup": setup}
    control_row = _run(_exec_cmd([]), control, directory / "control", "control_respawn_rebuild")
    treatment_row = _run(
        _exec_cmd(["resume", str(thread_id)]),
        treatment,
        directory / "treatment",
        "treatment_same_child_delta",
    )
    control_uncached = control_row["uncached_tokens"]
    treatment_uncached = treatment_row["uncached_tokens"]
    cheaper = (
        isinstance(control_uncached, int)
        and isinstance(treatment_uncached, int)
        and treatment_uncached < control_uncached
    )
    faster = (
        isinstance(control_row["elapsed_seconds"], (int, float))
        and isinstance(treatment_row["elapsed_seconds"], (int, float))
        and treatment_row["elapsed_seconds"] < control_row["elapsed_seconds"]
    )
    return {
        "gate": "live",
        "model": ACTIVE_MODEL,
        "pass": cheaper,
        "treatment_uncached_lt_control": cheaper,
        "treatment_faster": faster,
        "setup": setup,
        "control": control_row,
        "treatment": treatment_row,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("cheap", "live"), default="cheap")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--codex-home", type=Path, default=None)
    args = parser.parse_args()
    global PROFILE, ACTIVE_MODEL, CODEX_HOME
    PROFILE = args.profile
    ACTIVE_MODEL = args.model
    CODEX_HOME = args.codex_home
    if args.mode == "cheap":
        payload = cheap_ab()
    else:
        payload = live_ab()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    return 0 if payload.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
