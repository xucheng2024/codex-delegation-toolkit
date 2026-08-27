import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/orchestrate_workflow.py"
SPEC = importlib.util.spec_from_file_location("orchestrate_workflow", SCRIPT)
WORKFLOW = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(WORKFLOW)


def queue_request(**overrides):
    value = {
        "schema": WORKFLOW.QUEUE_INPUT_SCHEMA,
        "parent": "parent",
        "available": ["sol", "terra", "eco"],
        "complexity": {
            "A": 0, "B": 0, "U": 0, "preflight_complete": True,
            "evidence_truncated": False, "sol_pin": False, "terra_permit": False,
        },
        "allow_recursive_delegation": False,
        "current_delegation_depth": 0,
        "max_delegation_depth": 2,
        "delegation_available": True,
    }
    value.update(overrides)
    return value


def task(task_id, path, *, B=0, depends_on=()):
    return {
        "id": task_id, "objective": task_id, "owned_paths": [path],
        "depends_on": list(depends_on), "acceptance": "ok", "validation": "pytest",
        "A": 0, "B": B, "U": 0, "preflight_complete": True,
        "evidence_truncated": False,
    }


def graph(*tasks):
    items = tasks or (task("a", "a.py"), task("b", "b.py"))
    return {
        "schema": "codex-task-graph-v1",
        "integration_validation": ["pytest"],
        "tasks": list(items),
    }


ROLES = {"quality_first": "sol", "balanced": "terra", "economy": "eco"}


class WorkflowTests(unittest.TestCase):
    def test_single_task_enters_matching_queue(self):
        fast = WORKFLOW.decide_queue(queue_request(parent="terra"), roles=ROLES)
        self.assertEqual(fast["queue"], "fast")
        self.assertEqual(fast["execution_mode"], "single")
        self.assertEqual(fast["next_action"]["model"], "terra")
        self.assertEqual(fast["next_action"]["action"], "parent")
        self.assertEqual(fast["next_action"]["requested_model"], "eco")

        standard = WORKFLOW.decide_queue(queue_request(
            parent="terra", complexity={**queue_request()["complexity"], "B": 4},
        ), roles=ROLES)
        self.assertEqual(standard["queue"], "standard")
        self.assertEqual(standard["next_action"]["model"], "terra")
        self.assertEqual(standard["next_action"]["action"], "parent")

        complex_task = WORKFLOW.decide_queue(queue_request(
            parent="terra", complexity={**queue_request()["complexity"], "B": 8},
        ), roles=ROLES)
        self.assertEqual(complex_task["queue"], "complex")
        self.assertEqual(complex_task["next_action"]["model"], "sol")
        self.assertEqual(complex_task["next_action"]["action"], "spawn")

    def test_incomplete_preflight_blocks_before_queue_dispatch(self):
        for incomplete in ({"preflight_complete": False}, {"evidence_truncated": True}):
            with self.subTest(incomplete=incomplete):
                source = queue_request(complexity={**queue_request()["complexity"], **incomplete}, graph=graph())
                output = WORKFLOW.decide_queue(source, roles=ROLES)
                self.assertEqual(output["status"], "incomplete")
                self.assertEqual(output["queue"], "blocked")
                self.assertEqual(output["classification"]["required_steps"], ["complete-preflight"])
                self.assertNotIn("next_action", output)
                self.assertNotIn("schedule", output)

    def test_approved_graph_dispatches_without_economics(self):
        source = graph(
            task("fast", "a.py"),
            task("standard", "b.py", B=4),
            task("complex", "c.py", B=8, depends_on=("fast",)),
        )
        output = WORKFLOW.decide_queue(queue_request(parent="sol", graph=source), roles=ROLES)
        self.assertEqual(output["status"], "queued")
        self.assertEqual(output["execution_mode"], "waves")
        self.assertEqual(output["dispatch_mode"], "serial")
        self.assertEqual(output["failure_policy"], "stop-dependent-tasks")
        self.assertEqual(
            output["schedule"]["queues"],
            {"fast": ["fast"], "standard": ["standard"], "complex": ["complex"]},
        )
        emitted = {
            item["id"]: item for wave in output["schedule"]["waves"] for item in wave
        }
        self.assertEqual((emitted["fast"]["model"], emitted["fast"]["work_type"]), ("eco", "implement"))
        self.assertEqual((emitted["standard"]["model"], emitted["standard"]["work_type"]), ("terra", "implement"))
        self.assertEqual((emitted["complex"]["model"], emitted["complex"]["work_type"]), ("sol", "decompose"))
        self.assertNotIn("next_action", output)

    def test_graph_runs_serially_without_delegation_transport(self):
        source = queue_request(parent="sol", graph=graph())
        source.pop("delegation_available")
        output = WORKFLOW.decide_queue(source, roles=ROLES)
        self.assertEqual(output["dispatch_mode"], "serial")

    def test_graph_assigns_one_persistent_owner_per_queue(self):
        source = graph(*(task(name, f"{name}.py") for name in ("a", "b", "c", "d")))
        output = WORKFLOW.decide_queue(queue_request(parent="sol", graph=source), roles=ROLES)
        self.assertEqual(output["dispatch_mode"], "serial")
        self.assertEqual(
            output["schedule"]["owners"]["fast"],
            [{
                "id": "fast-1", "task_ids": ["a", "b", "c", "d"],
                "role": "economy", "model": "eco", "effort": "medium",
            }],
        )

    def test_three_ready_tasks_share_one_owner_serially(self):
        source = graph(*(task(name, f"{name}.py") for name in ("a", "b", "c")))
        output = WORKFLOW.decide_queue(queue_request(parent="sol", graph=source), roles=ROLES)
        self.assertEqual(output["dispatch_mode"], "serial")
        self.assertEqual(len(output["schedule"]["owners"]["fast"]), 1)

    def test_unavailable_queue_worker_fails_closed(self):
        with self.assertRaisesRegex(WORKFLOW.WorkflowError, "standard queue is unavailable"):
            WORKFLOW.decide_queue(
                queue_request(graph=graph(task("standard", "a.py", B=4)), available=["sol", "eco"]),
                roles=ROLES,
            )

    def test_economics_input_is_rejected(self):
        with self.assertRaisesRegex(WORKFLOW.WorkflowError, "missing or unknown"):
            WORKFLOW.decide_queue({**queue_request(), "economics": {}}, roles=ROLES)

    def test_strict_queue_request_and_after_implement_delegates_existing_escalation(self):
        with self.assertRaisesRegex(WORKFLOW.WorkflowError, "missing or unknown"):
            WORKFLOW.decide_queue({**queue_request(), "extra": True}, roles=ROLES)
        verification = {
            "schema": WORKFLOW.VERIFY_INPUT_SCHEMA, "parent": "parent",
            "available": ["sol", "terra"], "current_effort": "medium",
            "verifier": "fail", "delegation_available": True,
        }
        output = WORKFLOW.decide_after_implement(verification, roles=ROLES)
        self.assertEqual(output["next_action"]["action"], "retry")
        self.assertEqual(output["next_action"]["model"], "terra")

    def test_cli_dispatch_and_invalid_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(queue_request()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "dispatch", "--input", str(path)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["status"], "queued")
            path.write_text(json.dumps({"schema": WORKFLOW.QUEUE_INPUT_SCHEMA}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "dispatch", "--input", str(path)],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
