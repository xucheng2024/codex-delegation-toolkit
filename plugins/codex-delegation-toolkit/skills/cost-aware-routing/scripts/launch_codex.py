#!/usr/bin/env python3
"""Select an entry model locally, then launch the first Codex model call."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from classify_complexity import ComplexityError
from route_step import RouteError, load_role_map
from select_entry_model import select


RECEIPT_SCHEMA = "codex-entry-routing-receipt-v1"


class LaunchError(ValueError):
    """Raised when a safe pre-model launch cannot be constructed."""


def available_models(catalog: Any) -> set[str]:
    """Extract model slugs from a Codex model catalog."""
    if not isinstance(catalog, dict) or not isinstance(catalog.get("models"), list):
        raise LaunchError("model catalog must contain a models array")
    models = {
        item["slug"]
        for item in catalog["models"]
        if isinstance(item, dict) and isinstance(item.get("slug"), str)
    }
    if not models:
        raise LaunchError("model catalog contains no model slugs")
    return models


def read_catalog(codex_bin: str, catalog_file: Path | None, bundled: bool) -> Any:
    if catalog_file is not None:
        return json.loads(catalog_file.read_text(encoding="utf-8"))
    command = [codex_bin, "debug", "models"]
    if bundled:
        command.append("--bundled")
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or "model catalog command failed"
        raise LaunchError(detail)
    return json.loads(result.stdout)


def validate_codex_args(args: Sequence[str]) -> list[str]:
    normalized = list(args)
    if normalized[:1] == ["--"]:
        normalized = normalized[1:]
    for index, value in enumerate(normalized):
        if (
            value in {"-m", "--model"}
            or value.startswith("--model=")
            or value.startswith("-m=")
        ):
            raise LaunchError("pass model choice through the router, not codex arguments")
        if value in {"resume", "fork", "review"}:
            raise LaunchError("pre-model routing supports only a new codex exec turn")
        config_value = None
        if value in {"-c", "--config"} and index + 1 < len(normalized):
            config_value = normalized[index + 1]
        elif value.startswith("--config="):
            config_value = value.split("=", 1)[1]
        if config_value is not None:
            key = config_value.split("=", 1)[0]
            if key in {"model", "model_reasoning_effort"}:
                raise LaunchError(f"codex argument overrides routed {key}")
    return normalized


def build_codex_command(
    codex_bin: str, selection: dict[str, Any], codex_args: Sequence[str]
) -> list[str]:
    if selection.get("status") != "selected":
        raise LaunchError(selection.get("reason", "entry model was not selected"))
    model = selection.get("model")
    effort = selection.get("effort")
    if not isinstance(model, str) or not isinstance(effort, str):
        raise LaunchError("selection is missing model or effort")
    return [
        codex_bin,
        "exec",
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{effort}"',
        *validate_codex_args(codex_args),
        "-",
    ]


def routed_prompt(prompt: str, selection: dict[str, Any]) -> str:
    classification = selection["classification"]
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "entry_tier": classification["entry_tier"],
        "role": selection["role"],
        "model": selection["model"],
        "effort": selection["effort"],
    }
    return (
        "ENTRY_ROUTING_COMPLETE "
        + json.dumps(receipt, sort_keys=True, separators=(",", ":"))
        + "\nDo not invoke cost-aware-routing again unless deterministic validation "
        "fails or the supplied structural evidence proves incomplete.\n\n"
        + prompt
    )


def parser() -> argparse.ArgumentParser:
    here = Path(__file__).resolve().parent
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--role-map", type=Path, default=here.parent / "references" / "model-role-map.json")
    result.add_argument("--A", type=int, required=True, dest="a")
    result.add_argument("--B", type=int, required=True, dest="b")
    result.add_argument("--U", type=int, required=True, dest="u")
    result.add_argument("--preflight-complete", action="store_true")
    result.add_argument("--evidence-truncated", action="store_true")
    result.add_argument("--sol-pin", action="store_true")
    result.add_argument("--terra-permit", action="store_true")
    result.add_argument("--available", nargs="+")
    result.add_argument("--catalog-file", type=Path)
    result.add_argument("--bundled-catalog", action="store_true")
    result.add_argument("--codex-bin", default="codex")
    result.add_argument("--select-only", action="store_true")
    prompt_group = result.add_mutually_exclusive_group()
    prompt_group.add_argument("--prompt")
    prompt_group.add_argument("--prompt-file", type=Path)
    result.add_argument("codex_args", nargs=argparse.REMAINDER)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        roles = load_role_map(args.role_map)
        available = (
            set(args.available)
            if args.available
            else available_models(read_catalog(args.codex_bin, args.catalog_file, args.bundled_catalog))
        )
        selection = select(
            args.a,
            args.b,
            args.u,
            preflight_complete=args.preflight_complete,
            evidence_truncated=args.evidence_truncated,
            available=available,
            roles=roles,
            sol_pin=args.sol_pin,
            terra_permit=args.terra_permit,
        )
        if selection["status"] != "selected":
            print(json.dumps(selection, sort_keys=True))
            return 3
        if args.select_only:
            print(json.dumps(selection, sort_keys=True))
            return 0
        if args.prompt is not None:
            prompt = args.prompt
        elif args.prompt_file is not None:
            prompt = args.prompt_file.read_text(encoding="utf-8")
        elif not sys.stdin.isatty():
            prompt = sys.stdin.read()
        else:
            raise LaunchError("provide --prompt, --prompt-file, or piped stdin")
        if not prompt.strip():
            raise LaunchError("prompt must not be empty")
        command = build_codex_command(args.codex_bin, selection, args.codex_args)
        result = subprocess.run(command, input=routed_prompt(prompt, selection), text=True, check=False)
        return result.returncode
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ComplexityError,
        RouteError,
        LaunchError,
    ) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
