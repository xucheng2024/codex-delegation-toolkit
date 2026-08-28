import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/resource_leases.py"
SPEC = importlib.util.spec_from_file_location("resource_leases", SCRIPT)
LEASES = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(LEASES)


class ResourceLeaseTests(unittest.TestCase):
    def test_path_and_semantic_conflicts_wait_then_release(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "leases.json"
            acquired = LEASES.acquire(
                state, "migration", ["path:db", "resource:db:schema"], 60, now=100
            )
            self.assertEqual(acquired["status"], "acquired")
            child_path = LEASES.acquire(state, "api", ["path:db/orders.py"], 60, now=101)
            self.assertEqual(child_path, {
                "schema": LEASES.STATE_SCHEMA, "status": "waiting", "task_id": "api", "blockers": ["migration"],
            })
            semantic = LEASES.acquire(state, "reader", ["resource:db:schema"], 60, now=101)
            self.assertEqual(semantic["status"], "waiting")
            self.assertEqual(LEASES.release(state, "migration", now=102)["status"], "released")
            self.assertEqual(
                LEASES.acquire(state, "api", ["path:db/orders.py"], 60, now=103)["status"], "acquired"
            )

    def test_expiry_and_same_task_renewal_are_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "leases.json"
            LEASES.acquire(state, "task", ["path:a.py"], 5, now=100)
            renewal = LEASES.acquire(state, "task", ["path:b.py"], 10, now=102)
            self.assertEqual(renewal["resources"], ["path:b.py"])
            self.assertEqual(
                LEASES.acquire(state, "other", ["path:b.py"], 1, now=113)["status"], "acquired"
            )

    def test_cli_uses_waiting_exit_code_and_persists_strict_json(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "leases.json"
            first = subprocess.run(
                [sys.executable, str(SCRIPT), "--state", str(state), "acquire", "--task", "a", "--resource", "path:pkg", "--ttl-seconds", "60"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(first.returncode, 0)
            second = subprocess.run(
                [sys.executable, str(SCRIPT), "--state", str(state), "acquire", "--task", "b", "--resource", "path:pkg/file.py", "--ttl-seconds", "60"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(second.returncode, 3)
            self.assertEqual(json.loads(second.stdout)["status"], "waiting")


if __name__ == "__main__":
    unittest.main()
