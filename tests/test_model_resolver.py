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
                "id": "future-economy-x",
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
        self.assertEqual(output["roles"]["economy"]["model"], "future-economy-x")

    def test_override_must_remain_available_capable_and_under_ceiling(self):
        data = catalog()
        data["overrides"] = {"quality_first": "future-economy-x"}
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
    def test_typical_task_classes_follow_step_contract(self):
        spec = importlib.util.spec_from_file_location(
            "route_step",
            ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/route_step.py",
        )
        router = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(router)
        roles = router.load_role_map(ROLE_MAP)
        sol, terra, luna = roles["quality_first"], roles["balanced"], roles["economy"]
        available = {sol, terra, luna}
        cases = (
            ("bounded_edit", "implement", terra, False, False, "parent", terra),
            ("debug_and_tests", "implement", terra, False, False, "parent", terra),
            ("unpinned_sol_parent_implement", "implement", sol, False, False, "spawn", terra),
            ("hard_trigger_design", "judge", terra, False, False, "spawn", sol),
            ("independent_review", "judge", terra, False, False, "spawn", sol),
            ("explicit_sol_pin_implement", "implement", sol, True, False, "parent", sol),
            ("sol_pin_permits_terra_implement", "implement", sol, True, True, "spawn", terra),
            ("sol_unavailable", "judge", terra, False, False, "ask", sol),
        )
        sol_spawns = 0
        for name, step, parent, pin, permit, action, model in cases:
            models = {terra, luna} if name == "sol_unavailable" else available
            result = router.decide(step, parent, pin, permit, models, roles)
            self.assertEqual(result["action"], action, name)
            self.assertEqual(result["model"], model, name)
            if name == "sol_unavailable":
                self.assertEqual(result["status"], "ask")
                self.assertNotEqual(result["model"], terra)
            if action == "spawn" and model == sol:
                sol_spawns += 1
        self.assertEqual(sol_spawns, 2)


if __name__ == "__main__":
    unittest.main()
