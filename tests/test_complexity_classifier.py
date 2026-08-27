import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/classify_complexity.py"
SPEC = importlib.util.spec_from_file_location("classify_complexity", SCRIPT)
CLASSIFIER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CLASSIFIER)


class ComplexityClassifierTests(unittest.TestCase):
    def test_score_is_monotonic(self):
        base = CLASSIFIER.classify(0, 0, 0, preflight_complete=True)["score"]
        self.assertGreater(CLASSIFIER.classify(1, 0, 0, preflight_complete=True)["score"], base)
        self.assertGreater(CLASSIFIER.classify(0, 1, 0, preflight_complete=True)["score"], base)
        self.assertGreater(CLASSIFIER.classify(0, 0, 1, preflight_complete=True)["score"], base)

    def test_threshold_boundary_is_reviewed(self):
        fast = CLASSIFIER.classify(3, 1, 0, preflight_complete=True)
        boundary = CLASSIFIER.classify(0, 4, 0, preflight_complete=True)
        self.assertLess(fast["score"], CLASSIFIER.THRESHOLD)
        self.assertEqual(fast["effective_tier"], "fast")
        self.assertEqual(boundary["score"], CLASSIFIER.THRESHOLD)
        self.assertEqual(boundary["effective_tier"], "reviewed")
        self.assertEqual(fast["entry_tier"], "fast")
        self.assertEqual(boundary["entry_tier"], "standard")
        complex_result = CLASSIFIER.classify(0, 8, 0, preflight_complete=True)
        self.assertEqual(complex_result["entry_tier"], "complex")
        self.assertEqual(complex_result["entry_role"], "quality_first")

    def test_incomplete_or_truncated_evidence_never_routes_fast(self):
        for complete, truncated in ((False, False), (True, True)):
            result = CLASSIFIER.classify(
                0, 0, 0, preflight_complete=complete, evidence_truncated=truncated
            )
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["effective_tier"], "reviewed")
            self.assertEqual(result["entry_tier"], "complex")
            self.assertEqual(result["entry_role"], "quality_first")
            self.assertIsNone(result["implementation_role"])
            self.assertEqual(result["required_steps"], ["complete-preflight"])

        for flags in ((), ("--preflight-complete", "--evidence-truncated")):
            cli = subprocess.run(
                [sys.executable, str(SCRIPT), "--A", "0", "--B", "0", "--U", "0", *flags],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(cli.returncode, 3)
            output = json.loads(cli.stdout)
            self.assertEqual(output["status"], "incomplete")
            self.assertIsNone(output["implementation_role"])
            self.assertEqual(output["required_steps"], ["complete-preflight"])

    def test_explicit_controls_take_precedence(self):
        permitted = CLASSIFIER.classify(0, 0, 0, preflight_complete=True, terra_permit=True)
        pinned = CLASSIFIER.classify(
            0, 0, 0, preflight_complete=True, terra_permit=True, sol_pin=True
        )
        self.assertEqual(permitted["implementation_role"], "balanced")
        self.assertEqual(permitted["entry_tier"], "standard")
        self.assertEqual(permitted["required_steps"], ["implement", "validate", "self-review"])
        self.assertEqual(pinned["effective_tier"], "reviewed")
        self.assertEqual(pinned["required_steps"][0], "plan")

    def test_invalid_input_fails_closed(self):
        with self.assertRaisesRegex(CLASSIFIER.ComplexityError, "non-negative"):
            CLASSIFIER.classify(-1, 0, 0, preflight_complete=True)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--A", "-1", "--B", "0", "--U", "0", "--preflight-complete"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
