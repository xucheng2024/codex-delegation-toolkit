#!/usr/bin/env python3
"""Replay ten routing profiles against the pre-change and current policies."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ROUTER_PATH = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/route_step.py"
ROLE_MAP_PATH = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/references/model-role-map.json"


@dataclass(frozen=True)
class Profile:
    name: str
    step: str
    parent_role: str
    sol_pin: bool = False
    terra_permit: bool = False
    bounded: bool = False
    contract_complete: bool = False
    hard_packet: bool = False


PROFILES = (
    Profile("bounded_only_from_sol", "implement", "quality_first", bounded=True),
    Profile("contract_only_from_sol", "implement", "quality_first", contract_complete=True),
    Profile("bounded_complete_from_sol", "implement", "quality_first", bounded=True, contract_complete=True),
    Profile("hard_bounded_complete_from_sol", "implement", "quality_first", bounded=True, contract_complete=True, hard_packet=True),
    Profile("sol_pinned_review", "judge", "quality_first", sol_pin=True, bounded=True, contract_complete=True),
    Profile("terra_hard_review", "judge", "balanced", hard_packet=True),
    Profile("terra_soft_complete_implement", "implement", "balanced", bounded=True, contract_complete=True),
    Profile("sol_pinned_implement", "implement", "quality_first", sol_pin=True, bounded=True, contract_complete=True),
    Profile("bounded_only_from_luna", "implement", "economy", bounded=True),
    Profile("sol_pinned_review_with_terra_permit", "judge", "quality_first", sol_pin=True, terra_permit=True, bounded=True, contract_complete=True),
)


def load_router() -> Any:
    spec = importlib.util.spec_from_file_location("route_step", ROUTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load route_step.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def old_decide(profile: Profile, roles: dict[str, str]) -> dict[str, str]:
    """Exact decision order before the current policy changes."""
    sol, terra, luna = roles["quality_first"], roles["balanced"], roles["economy"]
    parent = roles[profile.parent_role]
    specified = profile.bounded or profile.contract_complete
    if profile.sol_pin and not profile.terra_permit:
        target, actor = sol, "parent" if parent == sol else "spawn"
    elif profile.step == "judge":
        target, actor = sol, "spawn"
    elif profile.sol_pin:
        target, actor = terra, "parent" if parent == terra else "spawn"
    elif specified and parent == terra:
        target, actor = terra, "parent"
    elif specified:
        target, actor = luna, "parent" if parent == luna else "thread"
    elif parent == terra:
        target, actor = terra, "parent"
    else:
        target, actor = terra, "spawn"
    return {"action": actor, "model": target}


def route_profile(profile: Profile, router: Any, roles: dict[str, str]) -> dict[str, dict[str, str]]:
    parent = roles[profile.parent_role]
    current = router.decide(
        profile.step,
        parent,
        profile.sol_pin,
        profile.terra_permit,
        set(roles.values()),
        roles,
        profile.bounded,
        profile.contract_complete,
        profile.hard_packet,
    )
    return {
        "before": old_decide(profile, roles),
        "after": {"action": current["action"], "model": current["model"]},
    }


def unsafe_incomplete_luna(profile: Profile, result: dict[str, str], roles: dict[str, str]) -> bool:
    return (
        profile.step == "implement"
        and result["model"] == roles["economy"]
        and not (profile.bounded and profile.contract_complete)
    )


def sol_self_review(profile: Profile, result: dict[str, str], roles: dict[str, str]) -> bool:
    return profile.step == "judge" and result["model"] == roles["quality_first"] and result["action"] == "parent"


def run() -> dict[str, object]:
    router = load_router()
    roles = router.load_role_map(ROLE_MAP_PATH)
    rows: list[dict[str, object]] = []
    for profile in PROFILES:
        routes = route_profile(profile, router, roles)
        before, after = routes["before"], routes["after"]
        rows.append(
            {
                "case": profile.name,
                "step": profile.step,
                "bounded": profile.bounded,
                "contract_complete": profile.contract_complete,
                "before": before,
                "after": after,
                "changed": before != after,
                "before_unsafe_luna": unsafe_incomplete_luna(profile, before, roles),
                "after_unsafe_luna": unsafe_incomplete_luna(profile, after, roles),
                "before_sol_self_review": sol_self_review(profile, before, roles),
                "after_sol_self_review": sol_self_review(profile, after, roles),
            }
        )
    count = lambda key: sum(bool(row[key]) for row in rows)
    sol_spawn_delta = sum(row["after"]["model"] == roles["quality_first"] and row["after"]["action"] == "spawn" for row in rows) - sum(row["before"]["model"] == roles["quality_first"] and row["before"]["action"] == "spawn" for row in rows)
    return {
        "experiment": "routing-policy-replay-v1",
        "profiles": len(rows),
        "results": rows,
        "summary": {
            "changed_routes": count("changed"),
            "unsafe_incomplete_luna_before": count("before_unsafe_luna"),
            "unsafe_incomplete_luna_after": count("after_unsafe_luna"),
            "sol_self_review_before": count("before_sol_self_review"),
            "sol_self_review_after": count("after_sol_self_review"),
            "sol_review_spawn_delta": sol_spawn_delta,
        },
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
