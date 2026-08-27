import importlib.util
import json
import math
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

    def test_record_workflow_writes_exact_privacy_safe_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["COST_AWARE_ROUTING_CACHE_DIR"] = temp_dir
            try:
                payload = RECORDER.record_workflow(
                    "reviewed", "dag", 3, 2, 2, 1.25, 42, True, 1
                )
                stored = json.loads((Path(temp_dir) / "workflows.jsonl").read_text())
            finally:
                os.environ.pop("COST_AWARE_ROUTING_CACHE_DIR", None)
        self.assertEqual(payload, stored)
        self.assertEqual(payload["schema"], "codex-workflow-outcome-v1")
        self.assertEqual(
            set(payload),
            {
                "schema", "ts", "repo", "complexity_bucket", "policy", "task_count",
                "dependency_count", "critical_path_length", "total_cost_units",
                "total_latency_ms", "final_pass", "rework_count",
            },
        )
        self.assertNotIn("prompt", payload)
        self.assertNotIn("path", payload)

    def test_record_workflow_rejects_invalid_values(self):
        invalid = (
            ("fast", "single", 0, 0, 1, 0, 0, False, 0, "task_count"),
            ("fast", "single", 1, -1, 1, 0, 0, False, 0, "dependency_count"),
            ("fast", "single", 1, 0, 2, 0, 0, False, 0, "critical_path_length"),
            ("fast", "single", 1, 0, 1, math.nan, 0, False, 0, "total_cost_units"),
            ("fast", "single", 1, 0, 1, math.inf, 0, False, 0, "total_cost_units"),
            ("fast", "single", 1, 0, 1, -1, 0, False, 0, "total_cost_units"),
            ("fast", "single", 1, 0, 1, 0, -1, False, 0, "total_latency_ms"),
            ("fast", "single", 1, 0, 1, 0, 0, "true", 0, "final_pass"),
            ("fast", "single", 1, 0, 1, 0, 0, False, -1, "rework_count"),
        )
        for *values, error in invalid:
            with self.subTest(error=error), self.assertRaisesRegex(RECORDER.RecordError, error):
                RECORDER.record_workflow(*values)

    def test_load_records_rejects_non_finite_existing_cost(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["COST_AWARE_ROUTING_CACHE_DIR"] = temp_dir
            try:
                path = Path(temp_dir) / "events.jsonl"
                path.write_text(
                    '{"schema":"codex-compute-event-v1","action":"stop","cost_usd":NaN}\n',
                    encoding="utf-8",
                )
                self.assertEqual(RECORDER.load_records(), [])
            finally:
                os.environ.pop("COST_AWARE_ROUTING_CACHE_DIR", None)

    def test_legacy_record_cli_and_schema_remain_compatible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["COST_AWARE_ROUTING_CACHE_DIR"] = temp_dir
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "record", "--step", "implement",
                    "--model", "gpt-5.6-terra", "--effort", "medium",
                    "--verifier", "pass", "--action", "stop",
                ],
                check=False, capture_output=True, text=True, env=env,
            )
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "codex-compute-event-v1")
        self.assertEqual(payload["success"], "unknown")

    def test_record_workflow_cli_rejects_extra_arguments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["COST_AWARE_ROUTING_CACHE_DIR"] = temp_dir
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "record-workflow", "--complexity-bucket", "fast",
                    "--policy", "single", "--task-count", "1", "--dependency-count", "0",
                    "--critical-path-length", "1", "--total-cost-units", "0",
                    "--total-latency-ms", "0", "--rework-count", "0", "--prompt", "secret",
                ],
                check=False, capture_output=True, text=True, env=env,
            )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("secret", result.stdout)

    def test_record_workflow_cli_writes_a_final_outcome(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["COST_AWARE_ROUTING_CACHE_DIR"] = temp_dir
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "record-workflow", "--complexity-bucket", "fast",
                    "--policy", "single", "--task-count", "1", "--dependency-count", "0",
                    "--critical-path-length", "1", "--total-cost-units", "0",
                    "--total-latency-ms", "0", "--final-pass", "--rework-count", "0",
                ],
                check=False, capture_output=True, text=True, env=env,
            )
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "codex-workflow-outcome-v1")
        self.assertTrue(payload["final_pass"])

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
