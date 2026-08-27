import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/schedule_task_graph.py"
SPEC = importlib.util.spec_from_file_location("schedule_task_graph", SCRIPT)
SCHEDULER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SCHEDULER)


def task(task_id, paths, depends_on=(), **overrides):
    value = {
        "id": task_id, "objective": f"implement {task_id}", "owned_paths": paths,
        "depends_on": list(depends_on), "acceptance": "accept", "validation": "pytest",
        "A": 0, "B": 0, "U": 0, "preflight_complete": True, "evidence_truncated": False,
    }
    value.update(overrides)
    return value


def graph(*tasks, integration_validation=None):
    return {
        "schema": SCHEDULER.INPUT_SCHEMA, "tasks": list(tasks),
        "integration_validation": integration_validation or ["python -m pytest -q"],
    }


class TaskGraphTests(unittest.TestCase):
    def test_strict_schema_and_types(self):
        with self.assertRaisesRegex(SCHEDULER.TaskGraphError, "only schema"):
            SCHEDULER.schedule({"schema": SCHEDULER.INPUT_SCHEMA, "tasks": [], "integration_validation": [], "extra": True})
        with self.assertRaisesRegex(SCHEDULER.TaskGraphError, "non-negative"):
            SCHEDULER.schedule(graph(task("a", ["a.py"], A=True)))
        with self.assertRaisesRegex(SCHEDULER.TaskGraphError, "boolean"):
            SCHEDULER.schedule(graph(task("a", ["a.py"], preflight_complete=1)))
        with self.assertRaisesRegex(SCHEDULER.TaskGraphError, "non-empty string"):
            SCHEDULER.schedule(graph(task("a", ["a.py"]), integration_validation=["  \t "]))

    def test_rejects_duplicate_unknown_self_and_cycle_dependencies(self):
        cases = (
            (graph(task("a", ["a.py"], ["a", "a"])), "duplicates"),
            (graph(task("a", ["a.py"], ["missing"])), "unknown"),
            (graph(task("a", ["a.py"], ["a"])), "itself"),
            (graph(task("a", ["a.py"], ["b"]), task("b", ["b.py"], ["a"])), "cycle"),
        )
        for value, error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(SCHEDULER.TaskGraphError, error):
                SCHEDULER.schedule(value)

    def test_rejects_invalid_paths_and_serializes_conflicting_paths(self):
        for path in ("/a.py", "", "a//b.py", "./a.py", "a/../b.py", "a\\b.py"):
            with self.subTest(path=path), self.assertRaises(SCHEDULER.TaskGraphError):
                SCHEDULER.schedule(graph(task("a", [path])))
        for paths in ((["a.py"], ["a.py"]), (["pkg"], ["pkg/a.py"])):
            with self.subTest(paths=paths):
                result = SCHEDULER.schedule(graph(task("a", paths[0]), task("b", paths[1])))
                self.assertEqual([[item["id"] for item in wave] for wave in result["waves"]], [["a"], ["b"]])

    def test_sibling_parallelism_and_dependency_serialization_are_deterministic(self):
        value = graph(
            task("z", ["z.py"]), task("a", ["a.py"]),
            task("dependent", ["d.py"], ["a"]),
        )
        result = SCHEDULER.schedule(value)
        self.assertEqual([[item["id"] for item in wave] for wave in result["waves"]], [["a", "z"], ["dependent"]])
        self.assertEqual(result["queues"], {"fast": ["a", "z", "dependent"], "standard": [], "complex": []})
        self.assertEqual(result["final_steps"], ["integration_validation", "judge"])

    def test_greedy_conflicting_ready_tasks_form_later_wave(self):
        result = SCHEDULER.schedule(graph(
            task("a", ["pkg"]), task("b", ["pkg/b.py"]), task("c", ["other.py"]),
        ))
        self.assertEqual([[item["id"] for item in wave] for wave in result["waves"]], [["a", "c"], ["b"]])

    def test_queue_length_never_adds_an_owner(self):
        fast = graph(*(task(name, [f"{name}.py"]) for name in ("a", "b", "c", "d")))
        fast_result = SCHEDULER.schedule(fast)
        self.assertEqual(
            fast_result["owners"]["fast"],
            [{"id": "fast-1", "task_ids": ["a", "b", "c", "d"]}],
        )

        standard = graph(*(
            task(name, [f"{name}.py"], B=4) for name in ("a", "b", "c", "d")
        ))
        self.assertEqual(len(SCHEDULER.schedule(standard)["owners"]["standard"]), 1)

        complex_graph = graph(*(
            task(name, [f"{name}.py"], B=8) for name in ("a", "b", "c", "d")
        ))
        self.assertEqual(len(SCHEDULER.schedule(complex_graph)["owners"]["complex"]), 1)

        seven = graph(*(task(f"t{index}", [f"t{index}.py"]) for index in range(7)))
        seven_result = SCHEDULER.schedule(seven)
        self.assertEqual(len(seven_result["owners"]["fast"]), 1)
        self.assertEqual(
            seven_result["owners"]["fast"][0]["task_ids"],
            [f"t{index}" for index in range(7)],
        )

    def test_one_owner_persists_across_dependency_waves(self):
        value = graph(
            task("seed", ["seed.py"]),
            *(task(name, [f"{name}.py"], ["seed"]) for name in ("a", "b", "c", "d")),
        )
        owners = SCHEDULER.schedule(value)["owners"]["fast"]
        self.assertEqual(owners, [{"id": "fast-1", "task_ids": ["seed", "a", "b", "c", "d"]}])

    def test_classifier_fields_are_preserved_and_incomplete_evidence_rejected(self):
        source = task("a", ["a.py"], A=1, B=2, U=0, sol_pin=True)
        result = SCHEDULER.schedule(graph(source))
        emitted = result["waves"][0][0]
        for field in ("A", "B", "U", "preflight_complete", "evidence_truncated", "sol_pin"):
            self.assertEqual(emitted[field], source[field])
        self.assertNotIn("terra_permit", emitted)
        self.assertEqual(emitted["classification"]["effective_tier"], "reviewed")
        self.assertEqual(emitted["queue"], "complex")
        self.assertEqual(emitted["work_type"], "decompose")
        with self.assertRaisesRegex(SCHEDULER.TaskGraphError, "incomplete"):
            SCHEDULER.schedule(graph(task("a", ["a.py"], preflight_complete=False)))
        with self.assertRaisesRegex(SCHEDULER.TaskGraphError, "incomplete"):
            SCHEDULER.schedule(graph(task("a", ["a.py"], evidence_truncated=True)))

    def test_recursive_delegation_requires_permission_and_depth_headroom(self):
        value = graph(task("a", ["a.py"]))
        denied = SCHEDULER.schedule(value)
        self.assertFalse(denied["waves"][0][0]["may_delegate"])
        self.assertNotIn("next_delegation_depth", denied["waves"][0][0])
        allowed = SCHEDULER.schedule(value, allow_recursive_delegation=True)
        self.assertEqual(allowed["waves"][0][0]["next_delegation_depth"], 1)
        exhausted = SCHEDULER.schedule(value, allow_recursive_delegation=True, current_delegation_depth=1, max_delegation_depth=1)
        self.assertFalse(exhausted["waves"][0][0]["may_delegate"])
        with self.assertRaisesRegex(SCHEDULER.TaskGraphError, "must not exceed"):
            SCHEDULER.schedule(value, current_delegation_depth=2, max_delegation_depth=1)

    def test_cli_rejects_invalid_depth(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "graph.json"
            input_path.write_text(json.dumps(graph(task("a", ["a.py"]))), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--input", str(input_path), "--current-delegation-depth", "2", "--max-delegation-depth", "1"],
                check=False, capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
