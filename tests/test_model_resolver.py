import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/resolve_model_roles.py"
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


if __name__ == "__main__":
    unittest.main()
