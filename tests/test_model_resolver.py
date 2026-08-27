import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/resolve_model_roles.py"
ROLE_MAP = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/references/model-role-map.json"
SPEC = importlib.util.spec_from_file_location("resolve_model_roles", SCRIPT)
RESOLVER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RESOLVER)


def catalog():
    return {
        "schema": "codex-model-catalog-v1",
        "models": [
            {
                "id": "future-frontier-z",
                "available": True,
                "quality_tier": 5,
                "cost_tier": 5,
                "latency_tier": 4,
                "capabilities": ["reasoning", "coding", "general"],
            },
            {
                "id": "future-balanced-y",
                "available": True,
                "quality_tier": 4,
                "cost_tier": 3,
                "latency_tier": 2,
                "capabilities": ["reasoning", "coding", "general"],
            },
            {
                "id": "future-coding-x",
                "available": True,
                "quality_tier": 3,
                "cost_tier": 1,
                "latency_tier": 1,
                "capabilities": ["coding", "general"],
            },
        ],
    }


class ModelResolverTests(unittest.TestCase):
    def test_resolves_arbitrary_future_model_names_by_role(self):
        output = RESOLVER.resolve(catalog())
        self.assertEqual(output["status"], "resolved")
        self.assertEqual(output["roles"]["quality_first"]["model"], "future-frontier-z")
        self.assertEqual(output["roles"]["balanced"]["model"], "future-balanced-y")
        self.assertEqual(output["roles"]["economy"]["model"], "future-coding-x")

    def test_economy_ranks_cost_then_latency_then_quality_and_id(self):
        data = catalog()
        data["models"].extend([
            {"id": "same-cost-slower", "available": True, "quality_tier": 5,
             "cost_tier": 1, "latency_tier": 2, "capabilities": ["coding"]},
            {"id": "same-cost-fast-weaker", "available": True, "quality_tier": 2,
             "cost_tier": 1, "latency_tier": 1, "capabilities": ["coding"]},
        ])
        self.assertEqual(RESOLVER.resolve(data)["roles"]["economy"]["model"], "future-coding-x")

    def test_override_must_remain_available_capable_and_under_ceiling(self):
        data = catalog()
        data["overrides"] = {"quality_first": "future-coding-x"}
        with self.assertRaisesRegex(RESOLVER.CatalogError, "incapable"):
            RESOLVER.resolve(data)

    def test_cost_ceiling_fails_closed_without_eligible_quality_model(self):
        data = catalog()
        data["max_cost_tier"] = 1
        output = RESOLVER.resolve(data)
        self.assertEqual(output["status"], "needs_input")
        self.assertEqual(output["unresolved_roles"], ["quality_first"])

    def test_unavailable_models_are_not_selected(self):
        data = catalog()
        data["models"][0]["available"] = False
        output = RESOLVER.resolve(data)
        self.assertEqual(output["roles"]["quality_first"]["model"], "future-balanced-y")

    def test_balanced_never_selects_a_strictly_dominated_model(self):
        data = catalog()
        data["models"] = [
            {
                "id": "stronger-cheaper-faster",
                "available": True,
                "quality_tier": 5,
                "cost_tier": 2,
                "latency_tier": 1,
                "capabilities": ["reasoning", "coding", "general"],
            },
            {
                "id": "weaker-costlier-slower",
                "available": True,
                "quality_tier": 2,
                "cost_tier": 4,
                "latency_tier": 5,
                "capabilities": ["reasoning", "coding", "general"],
            },
        ]
        output = RESOLVER.resolve(data)
        self.assertEqual(output["roles"]["balanced"]["model"], "stronger-cheaper-faster")

    def test_cli_output_is_bounded_and_does_not_echo_catalog(self):
        data = catalog()
        data["private_note"] = "do-not-echo-this"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--catalog", str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("do-not-echo-this", result.stdout)
        self.assertNotIn(str(path), result.stdout)
        self.assertEqual(json.loads(result.stdout)["schema"], "codex-model-routing-v1")

    def test_cli_read_error_does_not_echo_path(self):
        missing = Path("/private/catalogs/customer-secret.json")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--catalog", str(missing)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(str(missing), result.stdout)
        self.assertEqual(json.loads(result.stdout)["error"], "catalog could not be read")


class RoleMapTests(unittest.TestCase):
    def test_bundled_role_map_has_ids_without_availability_claims(self):
        data = json.loads(ROLE_MAP.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "codex-model-role-map-v1")
        self.assertEqual(
            data["roles"],
            {
                "quality_first": "gpt-5.6-sol",
                "balanced": "gpt-5.6-terra",
                "economy": "gpt-5.6-luna",
            },
        )
        self.assertNotIn("available", json.dumps(data))
        self.assertNotIn("models", data)


class RoutingMatrixTests(unittest.TestCase):
    def test_plan_review_always_spawns_a_fresh_quality_first_model(self):
        spec = importlib.util.spec_from_file_location(
            "route_step",
            ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/route_step.py",
        )
        router = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(router)
        roles = router.load_role_map(ROLE_MAP)
        quality_first, balanced = roles["quality_first"], roles["balanced"]

        result = router.decide(
            "plan-review", quality_first, False, False, {quality_first, balanced}, roles,
            delegation_available=True,
        )

        self.assertEqual(result["action"], "spawn")
        self.assertEqual(result["model"], quality_first)
        self.assertTrue(result["spawn"])

        cli = subprocess.run(
            [
                sys.executable,
                str(ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/route_step.py"),
                "--step", "plan-review", "--parent", quality_first,
                "--available", quality_first, balanced,
                "--delegation-available",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cli.returncode, 0)
        self.assertEqual(json.loads(cli.stdout)["action"], "spawn")

    def test_cli_independent_review_flag_preserves_default_local_judge(self):
        script = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/route_step.py"
        roles = json.loads(ROLE_MAP.read_text(encoding="utf-8"))["roles"]
        base = [
            sys.executable,
            str(script),
            "--step",
            "judge",
            "--parent",
            roles["quality_first"],
            "--available",
            roles["quality_first"],
            roles["balanced"],
        ]
        local = subprocess.run(base, check=False, capture_output=True, text=True)
        independent = subprocess.run(
            [*base, "--independent-review", "--delegation-available"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(local.returncode, 0)
        self.assertEqual(independent.returncode, 0)
        self.assertEqual(json.loads(local.stdout)["action"], "parent")
        self.assertEqual(json.loads(independent.stdout)["action"], "spawn")

    def test_typical_task_classes_follow_step_contract(self):
        spec = importlib.util.spec_from_file_location(
            "route_step",
            ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/route_step.py",
        )
        router = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(router)
        roles = router.load_role_map(ROLE_MAP)
        sol, terra = roles["quality_first"], roles["balanced"]
        available = {sol, terra}
        cases = (
            ("bounded_edit", "implement", terra, False, False, False, False, False, False, "parent", terra, "medium"),
            ("debug_and_tests", "implement", terra, False, False, False, False, False, False, "parent", terra, "medium"),
            ("unpinned_sol_parent_implement", "implement", sol, False, False, False, False, False, False, "spawn", terra, "medium"),
            ("bounded_without_contract_stays_terra", "implement", sol, False, False, True, False, False, False, "spawn", terra, "medium"),
            ("contract_without_bounded_stays_terra", "implement", sol, False, False, False, True, False, False, "spawn", terra, "medium"),
            ("bounded_complete_stays_terra", "implement", sol, False, False, True, True, False, False, "spawn", terra, "medium"),
            ("hard_bounded_complete_stays_terra", "implement", sol, False, False, True, True, True, False, "spawn", terra, "medium"),
            ("hard_without_contract_stays_terra", "implement", sol, False, False, False, False, True, False, "spawn", terra, "medium"),
            ("terra_parent_bounded_implement", "implement", terra, False, False, True, False, False, False, "parent", terra, "medium"),
            ("terra_parent_complete_contract", "implement", terra, False, False, False, True, False, False, "parent", terra, "medium"),
            ("explicit_sol_pin_implement", "implement", sol, True, False, True, True, True, False, "spawn", terra, "medium"),
            ("sol_pin_permits_terra_implement", "implement", sol, True, True, True, True, False, False, "spawn", terra, "medium"),
            ("terra_parent_sol_pin_implement", "implement", terra, True, False, False, False, False, False, "parent", terra, "medium"),
            ("terra_parent_plan", "plan", terra, False, False, False, False, False, False, "spawn", sol, "medium"),
            ("sol_parent_plans_itself", "plan", sol, False, False, False, False, False, False, "parent", sol, "medium"),
            ("sol_pin_plan", "plan", terra, True, False, False, False, False, False, "spawn", sol, "medium"),
            ("quality_first_parent_plan_review_spawns", "plan-review", sol, False, False, False, False, False, False, "spawn", sol, "medium"),
            ("terra_parent_judge_spawns_quality_first", "judge", terra, False, False, False, False, False, False, "spawn", sol, "medium"),
            ("independent_review_always_spawns", "judge", sol, False, False, False, False, False, True, "spawn", sol, "medium"),
            ("quality_first_parent_judges_locally", "judge", sol, True, False, True, True, False, False, "parent", sol, "medium"),
            ("sol_unavailable", "judge", terra, False, False, False, False, False, False, "ask", sol, "medium"),
            ("plan_sol_unavailable", "plan", terra, False, False, False, False, False, False, "ask", sol, "medium"),
        )
        sol_spawns = 0
        for case in cases:
            name, step, parent, pin, permit, bounded, complete, hard, independent, action, model, effort = case
            models = {terra} if action == "ask" else available
            result = router.decide(
                step, parent, pin, permit, models, roles, bounded, complete, hard,
                independent, delegation_available=True,
            )
            self.assertEqual(result["action"], action, name)
            self.assertEqual(result["model"], model, name)
            self.assertEqual(result["effort"], effort, name)
            if action == "spawn":
                self.assertEqual(result.get("spawn"), True, name)
            if action == "ask":
                self.assertEqual(result["status"], "ask", name)
                self.assertNotEqual(result["model"], terra, name)
            else:
                self.assertEqual(
                    set(result),
                    {"schema", "status", "action", "role", "model", "effort", "spawn"},
                    name,
                )
            if step == "implement":
                self.assertEqual(result["model"], terra, name)
            if action == "spawn" and model == sol:
                sol_spawns += 1
        self.assertEqual(sol_spawns, 5)

    def test_locality_uses_configured_role_map_values(self):
        spec = importlib.util.spec_from_file_location(
            "route_step",
            ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/route_step.py",
        )
        router = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(router)
        roles = {"quality_first": "custom-quality", "balanced": "custom-balanced"}
        available = set(roles.values())
        cases = (
            ("plan", "custom-quality", "parent", "custom-quality"),
            ("implement", "custom-balanced", "parent", "custom-balanced"),
            ("plan", "custom-balanced", "spawn", "custom-quality"),
            ("plan-review", "custom-quality", "spawn", "custom-quality"),
            ("plan-review", "custom-balanced", "spawn", "custom-quality"),
            ("implement", "custom-quality", "spawn", "custom-balanced"),
            ("judge", "custom-quality", "parent", "custom-quality"),
            ("judge", "custom-balanced", "spawn", "custom-quality"),
        )
        for step, parent, action, model in cases:
            with self.subTest(step=step, parent=parent):
                result = router.decide(
                    step, parent, False, False, available, roles,
                    delegation_available=True,
                )
                self.assertEqual(result["action"], action)
                self.assertEqual(result["model"], model)

    def test_fast_routing_stays_local_on_balanced_or_uses_available_economy(self):
        spec = importlib.util.spec_from_file_location(
            "route_step", ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/route_step.py"
        )
        router = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(router)
        legacy = {"quality_first": "sol", "balanced": "terra"}
        missing = router.decide("implement", "terra", False, False, {"sol", "terra"}, legacy, complexity_tier="fast")
        self.assertEqual(missing["status"], "routed")
        self.assertEqual(missing["model"], "terra")
        roles = {**legacy, "economy": "luna"}
        unavailable = router.decide("implement", "terra", False, False, {"sol", "terra"}, roles, complexity_tier="fast")
        self.assertEqual(unavailable["status"], "routed")
        self.assertEqual(unavailable["model"], "terra")
        unavailable_from_sol = router.decide(
            "implement", "sol", False, False, {"sol", "terra"}, roles,
            complexity_tier="fast", delegation_available=True,
        )
        self.assertEqual(unavailable_from_sol["status"], "ask")
        self.assertEqual(
            unavailable_from_sol["reason"],
            "target unavailable; disclose and ask or explicit degrade",
        )
        routed = router.decide(
            "implement", "terra", False, False, set(roles.values()), roles,
            complexity_tier="fast", delegation_available=True,
        )
        self.assertEqual(routed["action"], "parent")
        self.assertEqual(routed["role"], "balanced")
        self.assertEqual(routed["model"], "terra")

        delegated = router.decide(
            "implement", "sol", False, False, set(roles.values()), roles,
            complexity_tier="fast", delegation_available=True,
        )
        self.assertEqual(delegated["action"], "spawn")
        self.assertEqual(delegated["role"], "economy")
        self.assertEqual(delegated["model"], "luna")

        for sol_pin, terra_permit in ((True, False), (False, True), (True, True)):
            with self.subTest(sol_pin=sol_pin, terra_permit=terra_permit):
                protected = router.decide(
                    "implement", "terra", sol_pin, terra_permit, set(roles.values()), roles,
                    complexity_tier="fast", delegation_available=True,
                )
                self.assertEqual(protected["role"], "balanced")
                self.assertEqual(protected["model"], "terra")

        script = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/route_step.py"
        for flag in (("--sol-pin",), ("--terra-permit",), ("--sol-pin", "--terra-permit")):
            with self.subTest(flag=flag):
                cli = subprocess.run(
                    [
                        sys.executable, str(script), "--step", "implement", "--parent", "gpt-5.6-terra",
                        "--complexity-tier", "fast", *flag, "--available", "gpt-5.6-sol",
                        "gpt-5.6-terra", "gpt-5.6-luna", "--delegation-available",
                    ],
                    check=False, capture_output=True, text=True,
                )
                self.assertEqual(cli.returncode, 0)
                self.assertEqual(json.loads(cli.stdout)["role"], "balanced")

    def test_spawn_route_fails_safe_when_transport_is_unavailable(self):
        spec = importlib.util.spec_from_file_location(
            "route_step",
            ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/route_step.py",
        )
        router = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(router)
        roles = router.load_role_map(ROLE_MAP)
        result = router.decide(
            "judge",
            roles["balanced"],
            False,
            False,
            set(roles.values()),
            roles,
        )
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["action"], "parent")
        self.assertFalse(result["spawn"])
        self.assertEqual(result["requested_model"], roles["quality_first"])
        self.assertIn("never wait", result["reason"])

    def test_fast_unknown_parent_stays_on_current_without_guessing(self):
        spec = importlib.util.spec_from_file_location(
            "route_step",
            ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/route_step.py",
        )
        router = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(router)
        roles = router.load_role_map(ROLE_MAP)
        result = router.decide(
            "implement",
            "current",
            False,
            False,
            set(roles.values()),
            roles,
            complexity_tier="fast",
        )
        self.assertEqual(result["status"], "routed")
        self.assertEqual(result["action"], "parent")
        self.assertEqual(result["model"], "current")
        self.assertEqual(result["role"], "current")
        self.assertFalse(result["spawn"])


if __name__ == "__main__":
    unittest.main()
