import json
import subprocess
import sys
import unittest
from pathlib import Path

from experiments.adaptive_compute_replay import load_traces, score_policies


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests/fixtures/adaptive_compute_traces.json"
SCRIPT = ROOT / "experiments/adaptive_compute_replay.py"


class AdaptiveComputeReplayTests(unittest.TestCase):
    def test_fixture_scores_four_policies(self):
        result = score_policies(load_traces(FIXTURE))
        self.assertEqual(result["status"], "scored")
        policies = result["policies"]
        self.assertEqual(set(policies), {"always_stop", "adaptive", "always_high", "always_sol"})
        self.assertAlmostEqual(policies["always_stop"]["success_rate"], 0.25)
        self.assertAlmostEqual(policies["always_stop"]["upgrade_rate"], 0.0)
        self.assertAlmostEqual(policies["always_stop"]["mean_cost_usd"], 0.0775)
        self.assertAlmostEqual(policies["adaptive"]["success_rate"], 0.75)
        self.assertAlmostEqual(policies["adaptive"]["upgrade_rate"], 0.5)
        self.assertAlmostEqual(policies["adaptive"]["mean_cost_usd"], 0.225)
        self.assertAlmostEqual(policies["always_high"]["success_rate"], 0.5)
        self.assertAlmostEqual(policies["always_high"]["mean_cost_usd"], 0.1125)
        self.assertAlmostEqual(policies["always_sol"]["success_rate"], 1.0)
        self.assertAlmostEqual(policies["always_sol"]["mean_cost_usd"], 0.45)

    def test_omits_mean_cost_when_an_arm_has_none(self):
        tasks = load_traces(FIXTURE)
        del tasks[0]["arms"]["medium"]["cost_usd"]
        result = score_policies(tasks)
        self.assertNotIn("mean_cost_usd", result["policies"]["always_stop"])
        self.assertIn("success_rate", result["policies"]["always_stop"])

    def test_cli_does_not_echo_missing_path(self):
        missing = Path("/private/traces/customer-secret.json")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--traces", str(missing)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(str(missing), result.stdout)
        self.assertEqual(json.loads(result.stdout)["error"], "traces could not be read")


if __name__ == "__main__":
    unittest.main()
