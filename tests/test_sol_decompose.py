import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/sol_decompose.py"
SPEC = importlib.util.spec_from_file_location("sol_decompose", SCRIPT)
DECOMPOSER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(DECOMPOSER)


def graph(*, acceptance="accept", integration_validation=None):
    return {
        "schema": "codex-task-graph-v1",
        "tasks": [{
            "id": "leaf", "objective": "fix leaf", "owned_paths": ["app/leaf.py"],
            "depends_on": [], "acceptance": acceptance, "validation": "pytest -q",
            "A": 0, "B": 0, "U": 0, "preflight_complete": True,
            "evidence_truncated": False,
        }],
        "integration_validation": integration_validation or ["pytest -q"],
    }


def output_path(command):
    return Path(command[command.index("-o") + 1])


class SolDecomposeTests(unittest.TestCase):
    def test_invalid_initial_graph_is_repaired_using_only_its_new_thread(self):
        calls = []

        def runner(command, input_text):
            calls.append((list(command), input_text))
            if command[1:3] == ["exec", "--json"]:
                output_path(command).write_text(json.dumps(graph(acceptance=["accept"], integration_validation="pytest -q")), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, '{"type":"thread.started","thread_id":"new-sol-thread"}\n', "")
            self.assertEqual(command[1:3], ["exec", "resume"])
            self.assertEqual(command[4], "new-sol-thread")
            self.assertIsNone(input_text)
            self.assertIn("task.acceptance", command[-1])
            self.assertIn("preflight_complete", command[-1])
            output_path(command).write_text(json.dumps(graph()), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "graph.json"
            receipt = DECOMPOSER.decompose("decompose this", output=output, runner=runner)
            self.assertTrue(receipt["schema_repair_used"])
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), graph())
        self.assertEqual(len(calls), 2)

    def test_invalid_repair_never_writes_or_schedules_a_graph(self):
        calls = []

        def runner(command, input_text):
            calls.append(list(command))
            output_path(command).write_text(json.dumps(graph(acceptance=[])), encoding="utf-8")
            if command[1:3] == ["exec", "--json"]:
                return subprocess.CompletedProcess(command, 0, '{"type":"thread.started","thread_id":"new-sol-thread"}\n', "")
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "graph.json"
            with self.assertRaisesRegex(DECOMPOSER.DecompositionError, "non-empty string"):
                DECOMPOSER.decompose("decompose this", output=output, runner=runner)
            self.assertFalse(output.exists())
        self.assertEqual(len(calls), 2)

    def test_missing_or_ambiguous_thread_event_cannot_resume(self):
        with self.assertRaisesRegex(DECOMPOSER.DecompositionError, "exactly one"):
            DECOMPOSER.extract_started_thread("")
        with self.assertRaisesRegex(DECOMPOSER.DecompositionError, "exactly one"):
            DECOMPOSER.extract_started_thread(
                '{"type":"thread.started","thread_id":"one"}\n'
                '{"type":"thread.started","thread_id":"two"}\n'
            )


if __name__ == "__main__":
    unittest.main()
