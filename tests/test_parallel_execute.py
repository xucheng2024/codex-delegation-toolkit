import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/parallel_execute.py"
SPEC = importlib.util.spec_from_file_location("parallel_execute", SCRIPT)
EXECUTOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(EXECUTOR)


def task(task_id, path):
    return {
        "id": task_id, "owned_paths": [path], "lease_resources": [f"path:{path}"],
        "model": "fake", "effort": "medium", "work_type": "implement",
        "objective": task_id, "acceptance": "written", "validation": f"test -f {path}",
    }


def decision(*waves):
    return {
        "schema": EXECUTOR.INPUT_SCHEMA, "status": "queued", "dispatch_mode": "parallel-leased",
        "max_parallelism": 2, "schedule": {"waves": [list(wave) for wave in waves], "integration_validation": ["test -f a.txt", "test -f b.txt"]},
    }


class ParallelExecutorTests(unittest.TestCase):
    def test_rejects_nonparallel_or_nonleaf_inputs(self):
        with self.assertRaisesRegex(EXECUTOR.ExecutionError, "parallel-leased"):
            EXECUTOR._validate_decision({"schema": EXECUTOR.INPUT_SCHEMA})
        invalid = decision((task("a", "a.txt"),))
        invalid["schedule"]["waves"][0][0]["work_type"] = "decompose"
        with self.assertRaisesRegex(EXECUTOR.ExecutionError, "implementation leaves"):
            EXECUTOR._validate_decision(invalid)

    def test_parallel_workers_merge_only_after_validated_waves(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
            subprocess.run(["git", "add", "seed.txt"], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True)
            fake = root / "fake-codex.py"
            fake.write_text(
                "#!/usr/bin/env python3\nimport json, pathlib, sys\npacket=json.loads(sys.stdin.read().split('\\n', 1)[1])\npathlib.Path(packet['owned_paths'][0]).write_text(packet['id'], encoding='utf-8')\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            output = EXECUTOR.execute(
                decision((task("a", "a.txt"), task("b", "b.txt"))),
                repo=repo, lease_state=root / "leases.json", worktree_root=root / "worktrees", codex_bin=str(fake),
            )
            self.assertEqual(output["status"], "completed")
            self.assertEqual((repo / "a.txt").read_text(encoding="utf-8"), "a")
            self.assertEqual((repo / "b.txt").read_text(encoding="utf-8"), "b")
            self.assertEqual(subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True).stdout.count("worktree "), 1)


if __name__ == "__main__":
    unittest.main()
