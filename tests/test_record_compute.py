import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/record_compute.py"
SPEC = importlib.util.spec_from_file_location("record_compute", SCRIPT)
RECORDER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RECORDER)


class RecordComputeTests(unittest.TestCase):
    def test_records_allowed_fields_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["COST_AWARE_ROUTING_CACHE_DIR"] = temp_dir
            try:
                payload = RECORDER.record(
                    "implement",
                    "gpt-5.6-terra",
                    "medium",
                    "fail",
                    "retry_high",
                    "unknown",
                    hard_packet=True,
                    input_tokens=120,
                    cost_usd=0.08,
                )
                stats = RECORDER.format_stats(RECORDER.load_records())
            finally:
                os.environ.pop("COST_AWARE_ROUTING_CACHE_DIR", None)
        self.assertEqual(payload["schema"], "codex-compute-event-v1")
        self.assertEqual(payload["action"], "retry_high")
        self.assertEqual(payload["input_tokens"], 120)
        self.assertEqual(payload["cost_usd"], 0.08)
        self.assertNotIn("prompt", payload)
        self.assertNotIn("diff", payload)
        self.assertNotIn("reason", payload)
        self.assertIn("retry_high=1", stats)
        self.assertNotIn("gpt-5.6-terra", stats)

    def test_rejects_path_like_model_and_negative_usage(self):
        with self.assertRaisesRegex(RECORDER.RecordError, "short identifier"):
            RECORDER.record("implement", "/secret/prompt.md", "medium", "pass", "stop")
        with self.assertRaisesRegex(RECORDER.RecordError, "non-negative"):
            RECORDER.record(
                "implement",
                "gpt-5.6-terra",
                "medium",
                "pass",
                "stop",
                input_tokens=-1,
            )

    def test_cli_does_not_echo_invalid_model(self):
        secret = "/private/customer/prompt.md"
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["COST_AWARE_ROUTING_CACHE_DIR"] = temp_dir
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "record",
                    "--step",
                    "implement",
                    "--model",
                    secret,
                    "--effort",
                    "medium",
                    "--verifier",
                    "pass",
                    "--action",
                    "stop",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(secret, result.stdout)
        self.assertEqual(json.loads(result.stdout)["error"], "model must be a short identifier")


if __name__ == "__main__":
    unittest.main()
