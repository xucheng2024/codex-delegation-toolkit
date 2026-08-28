#!/usr/bin/env python3
"""Low-cost, live A/B measurement for serial versus parallel Codex workflows."""
from __future__ import annotations
import argparse, json, statistics, subprocess, time
from pathlib import Path
from typing import Any

SCHEMA = "codex-parallel-ab-v1"
class ABError(ValueError): pass

def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0: raise ABError(f"{field} must be a non-negative number")
    return float(value)

def load_rates(path: Path) -> dict[str, dict[str, float]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != "codex-model-rates-v1" or not isinstance(value.get("models"), dict): raise ABError("rate card schema must be codex-model-rates-v1")
    return {model: {key: _number(rate.get(key, 0), f"rates.{model}.{key}") for key in ("input", "cached_input", "output", "reasoning")} for model, rate in value["models"].items() if isinstance(model, str) and isinstance(rate, dict)}

def load_usage(path: Path, rates: dict[str, dict[str, float]]) -> tuple[float | None, int]:
    if not path.is_file(): return None, 0
    total = 0.0; rows = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        item = json.loads(line); model = item.get("model") if isinstance(item, dict) else None
        if not isinstance(model, str) or model not in rates: raise ABError("usage requires a model with configured price")
        total += sum(_number(item.get(key, 0), f"usage.{key}") * rates[model][key] / 1_000_000 for key in rates[model]); rows += 1
    return total, rows

def run_arm(name: str, command: str, usage: Path, rates: dict[str, dict[str, float]]) -> dict[str, Any]:
    started = time.monotonic(); result = subprocess.run(["sh", "-lc", command], check=False)
    cost, usage_rows = load_usage(usage, rates)
    return {"arm": name, "elapsed_ms": round((time.monotonic() - started) * 1000), "success": result.returncode == 0, "cost_usd": cost, "usage_rows": usage_rows}

def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    arms = {}
    for name in ("serial", "parallel"):
        selected = [row for row in rows if row["arm"] == name]; costs = [row["cost_usd"] for row in selected if row["cost_usd"] is not None]
        arms[name] = {"success_rate": sum(row["success"] for row in selected) / len(selected), "median_elapsed_ms": round(statistics.median(row["elapsed_ms"] for row in selected)), "mean_cost_usd": sum(costs) / len(costs) if len(costs) == len(selected) else None}
    serial, parallel = arms["serial"], arms["parallel"]
    return {"schema": SCHEMA, "runs": len(rows) // 2, "arms": arms, "directional": {"time_saved_ms": serial["median_elapsed_ms"] - parallel["median_elapsed_ms"], "cost_delta_usd": None if serial["mean_cost_usd"] is None or parallel["mean_cost_usd"] is None else parallel["mean_cost_usd"] - serial["mean_cost_usd"], "note": "directional only; increase repeat only after the first sample is useful"}}

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial-command", required=True); parser.add_argument("--parallel-command", required=True)
    parser.add_argument("--serial-usage", type=Path, required=True); parser.add_argument("--parallel-usage", type=Path, required=True); parser.add_argument("--rates", type=Path, required=True); parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        if args.repeat < 1 or args.repeat > 3: raise ABError("repeat must be between one and three")
        rates = load_rates(args.rates); rows = []
        for index in range(args.repeat):
            for name, command, usage in (("serial", args.serial_command, args.serial_usage), ("parallel", args.parallel_command, args.parallel_usage)):
                print(json.dumps({"schema": SCHEMA, "status": "running", "sample": index + 1, "arm": name}), flush=True); rows.append(run_arm(name, command, usage, rates))
        print(json.dumps(summarize(rows), sort_keys=True, allow_nan=False)); return 0
    except (OSError, UnicodeError, json.JSONDecodeError, ABError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "invalid", "error": str(exc)})); return 2
if __name__ == "__main__": raise SystemExit(main())
