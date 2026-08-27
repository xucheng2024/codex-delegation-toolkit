import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/select_entry_model.py"
ROLE_MAP = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/references/model-role-map.json"
SPEC = importlib.util.spec_from_file_location("select_entry_model", SCRIPT)
SELECTOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SELECTOR)
ROLES = {"quality_first": "sol", "balanced": "terra", "economy": "luna"}
AVAILABLE = set(ROLES.values())


class EntryModelSelectorTests(unittest.TestCase):
    def test_fast_selects_luna_medium_without_parallelism(self):
        output = SELECTOR.select(
            1, 0, 0, preflight_complete=True, evidence_truncated=False,
            available=AVAILABLE, roles=ROLES,
        )
        self.assertEqual(output["status"], "selected")
        self.assertEqual(output["model"], "luna")
        self.assertEqual(output["effort"], "medium")
        self.assertEqual(output["parallel_policy"], "none")

    def test_standard_selects_terra_and_defers_parallelism_until_plan(self):
        output = SELECTOR.select(
            8, 1, 0, preflight_complete=True, evidence_truncated=False,
            available=AVAILABLE, roles=ROLES,
        )
        self.assertEqual(output["model"], "terra")
        self.assertEqual(output["parallel_policy"], "evaluate_after_approved_graph")

    def test_complex_selects_sol(self):
        output = SELECTOR.select(
            0, 8, 0, preflight_complete=True, evidence_truncated=False,
            available=AVAILABLE, roles=ROLES,
        )
        self.assertEqual(output["model"], "sol")

    def test_incomplete_preflight_fails_up_to_sol(self):
        output = SELECTOR.select(
            1, 0, 0, preflight_complete=False, evidence_truncated=False,
            available=AVAILABLE, roles=ROLES,
        )
        self.assertEqual(output["model"], "sol")
        self.assertEqual(output["classification"]["status"], "incomplete")

    def test_terra_permit_selects_terra(self):
        output = SELECTOR.select(
            1, 0, 0, preflight_complete=True, evidence_truncated=False,
            terra_permit=True, available=AVAILABLE, roles=ROLES,
        )
        self.assertEqual(output["model"], "terra")

    def test_unavailable_model_needs_input(self):
        output = SELECTOR.select(
            1, 0, 0, preflight_complete=True, evidence_truncated=False,
            available={"sol", "terra"}, roles=ROLES,
        )
        self.assertEqual(output["status"], "needs_input")
        self.assertEqual(output["model"], "luna")

    def test_cli_outputs_selected_model(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--role-map",
                str(ROLE_MAP),
                "--A",
                "1",
                "--B",
                "0",
                "--U",
                "0",
                "--preflight-complete",
                "--available",
                "gpt-5.6-sol",
                "gpt-5.6-terra",
                "gpt-5.6-luna",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["model"], "gpt-5.6-luna")


if __name__ == "__main__":
    unittest.main()
