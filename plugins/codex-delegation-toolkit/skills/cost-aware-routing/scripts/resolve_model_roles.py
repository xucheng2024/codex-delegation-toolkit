#!/usr/bin/env python3
"""Resolve durable workload roles from a trusted, provider-neutral model catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "codex-model-catalog-v1"
OUTPUT_SCHEMA = "codex-model-routing-v1"
MAX_CATALOG_CHARS = 1_000_000
ROLES = ("quality_first", "balanced")
DEFAULT_REQUIREMENTS = {
    "quality_first": ("reasoning",),
    "balanced": ("coding",),
}


class CatalogError(ValueError):
    """Raised when a catalog cannot be trusted for deterministic routing."""


def _tier(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise CatalogError(f"{field} must be an integer from 1 through 5")
    return value


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise CatalogError(f"{field} must be a list of non-empty strings")
    return tuple(value)


def _parse_catalog(data: Any) -> tuple[list[dict[str, Any]], dict[str, tuple[str, ...]], dict[str, str], int]:
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise CatalogError(f"schema must be {SCHEMA}")

    raw_models = data.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise CatalogError("models must be a non-empty list")

    models: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_models):
        if not isinstance(raw, dict):
            raise CatalogError(f"models[{index}] must be an object")
        model_id = raw.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise CatalogError(f"models[{index}].id must be a non-empty string")
        if model_id in seen_ids:
            raise CatalogError("model ids must be unique")
        seen_ids.add(model_id)
        available = raw.get("available")
        if not isinstance(available, bool):
            raise CatalogError(f"models[{index}].available must be a boolean")
        models.append(
            {
                "id": model_id,
                "available": available,
                "quality": _tier(raw.get("quality_tier"), f"models[{index}].quality_tier"),
                "cost": _tier(raw.get("cost_tier"), f"models[{index}].cost_tier"),
                "latency": _tier(raw.get("latency_tier"), f"models[{index}].latency_tier"),
                "capabilities": set(_string_list(raw.get("capabilities"), f"models[{index}].capabilities")),
            }
        )

    requirements = dict(DEFAULT_REQUIREMENTS)
    raw_requirements = data.get("role_requirements", {})
    if not isinstance(raw_requirements, dict) or any(role not in ROLES for role in raw_requirements):
        raise CatalogError("role_requirements contains an unknown role")
    for role, capabilities in raw_requirements.items():
        requirements[role] = _string_list(capabilities, f"role_requirements.{role}")

    raw_overrides = data.get("overrides", {})
    if not isinstance(raw_overrides, dict) or any(role not in ROLES for role in raw_overrides):
        raise CatalogError("overrides contains an unknown role")
    overrides: dict[str, str] = {}
    for role, model_id in raw_overrides.items():
        if not isinstance(model_id, str) or not model_id:
            raise CatalogError(f"overrides.{role} must be a non-empty model id")
        overrides[role] = model_id

    max_cost = _tier(data.get("max_cost_tier", 5), "max_cost_tier")
    return models, requirements, overrides, max_cost


def _rank(role: str, model: dict[str, Any]) -> tuple[Any, ...]:
    if role == "quality_first":
        return (-model["quality"], model["cost"], model["latency"], model["id"])
    if role == "balanced":
        shortfall = 6 - model["quality"]
        return (
            2 * model["cost"] + shortfall**2 + model["latency"],
            -model["quality"],
            model["cost"],
            model["latency"],
            model["id"],
        )
    raise CatalogError(f"unknown role: {role}")


def resolve(data: Any) -> dict[str, Any]:
    models, requirements, overrides, max_cost = _parse_catalog(data)
    by_id = {model["id"]: model for model in models}
    result: dict[str, dict[str, str]] = {}
    unresolved: list[str] = []

    for role in ROLES:
        required = set(requirements[role])
        eligible = [
            model
            for model in models
            if model["available"]
            and model["cost"] <= max_cost
            and required.issubset(model["capabilities"])
        ]
        override_id = overrides.get(role)
        if override_id is not None:
            override = by_id.get(override_id)
            if override not in eligible:
                raise CatalogError(f"override for {role} is unavailable, over budget, or incapable")
            result[role] = {"model": override_id, "source": "override"}
        elif eligible:
            selected = min(eligible, key=lambda model: _rank(role, model))
            result[role] = {"model": selected["id"], "source": "catalog"}
        else:
            unresolved.append(role)

    return {
        "schema": OUTPUT_SCHEMA,
        "status": "resolved" if not unresolved else "needs_input",
        "roles": result,
        "unresolved_roles": unresolved,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        with args.catalog.open(encoding="utf-8") as catalog_file:
            raw_catalog = catalog_file.read(MAX_CATALOG_CHARS + 1)
        if len(raw_catalog) > MAX_CATALOG_CHARS:
            raise CatalogError("catalog exceeds the size limit")
        data = json.loads(raw_catalog)
        output = resolve(data)
    except OSError:
        error = "catalog could not be read"
    except (UnicodeError, json.JSONDecodeError):
        error = "catalog is not valid UTF-8 JSON"
    except CatalogError as exc:
        error = str(exc)
    else:
        print(json.dumps(output, sort_keys=True))
        return 0 if output["status"] == "resolved" else 3

    print(json.dumps({"schema": OUTPUT_SCHEMA, "status": "invalid", "error": error}))
    return 2


if __name__ == "__main__":
    sys.exit(main())
