import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/escalate_step.py"
ROLE_MAP = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/references/model-role-map.json"
SPEC = importlib.util.spec_from_file_location("escalate_step", SCRIPT)
ESCALATE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ESCALATE)


class EscalateStepTests(unittest.TestCase):
    def setUp(self):
        self.roles = ESCALATE.load_role_map(ROLE_MAP)
        self.sol = self.roles["quality_first"]
        self.terra = self.roles["balanced"]
        self.available = {self.sol, self.terra}

    def decide(self, step, effort, verifier, parent=None, available=None):
        return ESCALATE.decide(
            step,
            effort,
            verifier,
            parent or self.terra,
            available if available is not None else self.available,
            self.roles,
        )

    def test_pass_stops_without_upgrade(self):
        result = self.decide("implement", "medium", "pass")
        self.assertEqual(result["action"], "stop")
        self.assertEqual(result["effort"], "medium")
        self.assertFalse(result["spawn"])

    def test_implement_fail_or_incomplete_retries_terra_high(self):
        for verifier in ("fail", "incomplete"):
            result = self.decide("implement", "medium", verifier)
            self.assertEqual(result["action"], "retry", verifier)
            self.assertEqual(result["model"], self.terra, verifier)
            self.assertEqual(result["effort"], "high", verifier)
            self.assertEqual(result["step"], "implement", verifier)
            self.assertFalse(result["spawn"], verifier)

    def test_sol_parent_retry_spawns_terra(self):
        result = self.decide("implement", "medium", "fail", parent=self.sol)
        self.assertEqual(result["action"], "retry")
        self.assertEqual(result["model"], self.terra)
        self.assertTrue(result["spawn"])

    def test_high_fail_spawns_sol_judge(self):
        result = self.decide("implement", "high", "fail")
        self.assertEqual(result["action"], "spawn")
        self.assertEqual(result["role"], "quality_first")
        self.assertEqual(result["model"], self.sol)
        self.assertEqual(result["step"], "judge")
        self.assertEqual(result["effort"], "medium")
        self.assertTrue(result["spawn"])

    def test_plan_and_judge_failures_stop(self):
        for step in ("plan", "judge"):
            result = self.decide(step, "medium", "fail")
            self.assertEqual(result["action"], "stop", step)
            self.assertFalse(result["spawn"], step)

    def test_unavailable_target_asks(self):
        retry = self.decide("implement", "medium", "fail", available={self.sol})
        self.assertEqual(retry["action"], "ask")
        self.assertEqual(retry["model"], self.terra)
        judge = self.decide("implement", "high", "fail", available={self.terra})
        self.assertEqual(judge["action"], "ask")
        self.assertEqual(judge["model"], self.sol)

    def test_cli_honors_matrix(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--step",
                "implement",
                "--current-effort",
                "medium",
                "--verifier",
                "fail",
                "--parent",
                self.terra,
                "--available",
                self.terra,
                self.sol,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        self.assertEqual(output["action"], "retry")
        self.assertEqual(output["effort"], "high")


if __name__ == "__main__":
    unittest.main()
