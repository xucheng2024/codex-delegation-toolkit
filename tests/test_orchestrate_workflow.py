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


def plan(**overrides):
    value = {
        "schema": WORKFLOW.PLAN_INPUT_SCHEMA, "parent": "parent", "available": ["sol", "terra", "eco"],
        "complexity": {"A": 0, "B": 0, "U": 0, "preflight_complete": True, "evidence_truncated": False, "sol_pin": False, "terra_permit": False},
        "allow_recursive_delegation": False, "current_delegation_depth": 0, "max_delegation_depth": 2,
        "delegation_available": True,
    }
    value.update(overrides)
    return value


def graph():
    return {
        "schema": "codex-task-graph-v1", "integration_validation": ["pytest"],
        "tasks": [
            {"id": "a", "objective": "a", "owned_paths": ["a.py"], "depends_on": [], "acceptance": "ok", "validation": "pytest", "A": 0, "B": 0, "U": 0, "preflight_complete": True, "evidence_truncated": False},
            {"id": "b", "objective": "b", "owned_paths": ["b.py"], "depends_on": [], "acceptance": "ok", "validation": "pytest", "A": 0, "B": 0, "U": 0, "preflight_complete": True, "evidence_truncated": False},
        ],
    }


ROLES = {"quality_first": "sol", "balanced": "terra", "economy": "eco"}


class WorkflowTests(unittest.TestCase):
    def test_no_economics_uses_single_and_delegates_existing_fast_route(self):
        output = WORKFLOW.decide_plan(plan(parent="terra"), roles=ROLES)
        self.assertEqual(output["split_decision"], {"status": "insufficient", "selected": "single", "reason": "economics unavailable"})
        self.assertEqual(output["execution_mode"], "single")
        self.assertEqual(output["next_action"]["model"], "terra")
        self.assertEqual(output["next_action"]["action"], "parent")

    def test_incomplete_preflight_short_circuits_schedule_economics_and_routing(self):
        for incomplete in ({"preflight_complete": False}, {"evidence_truncated": True}):
            with self.subTest(incomplete=incomplete):
                source = plan(complexity={**plan()["complexity"], **incomplete}, graph=graph(), economics={})
                output = WORKFLOW.decide_plan(source, roles=ROLES)
                self.assertEqual(output["status"], "incomplete")
                self.assertEqual(output["classification"]["required_steps"], ["complete-preflight"])
                self.assertEqual(output["execution_mode"], "single")
                self.assertEqual(output["split_decision"], {"status": "not-evaluated", "selected": "single", "reason": "preflight incomplete"})
                self.assertNotIn("next_action", output)
                self.assertNotIn("schedule", output)

    def test_dag_cost_latency_and_gain_select_dag(self):
        economics = {
            "latency_weight": 1, "minimum_gain_ratio": 0.1,
            "single": {"cost_units": 10, "latency_ms": 100, "success_probability": 1},
            "dag": {"overhead_cost_units": 2, "overhead_latency_ms": 5, "success_probability": 1,
                    "tasks": {"a": {"cost_units": 3, "latency_ms": 20}, "b": {"cost_units": 3, "latency_ms": 30}}},
        }
        output = WORKFLOW.decide_plan(plan(graph=graph(), economics=economics), roles=ROLES)
        decision = output["split_decision"]
        self.assertEqual(decision["selected"], "dag")
        self.assertEqual(decision["single_score"], 110)
        self.assertEqual(decision["dag_score"], 43)
        self.assertAlmostEqual(decision["gain_ratio"], 67 / 110)
        self.assertEqual(output["schedule"]["waves"][0][0]["id"], "a")

    def test_standard_workflow_stays_on_terra_after_local_plan(self):
        source = plan(
            parent="terra",
            complexity={**plan()["complexity"], "A": 8, "B": 1},
            graph=graph(),
        )
        output = WORKFLOW.decide_plan(source, roles=ROLES)
        self.assertEqual(output["classification"]["entry_tier"], "standard")
        self.assertEqual(output["next_action"]["action"], "parent")
        self.assertEqual(output["next_action"]["model"], "terra")

    def test_complex_workflow_plans_once_then_implements_approved_graph(self):
        complexity = {**plan()["complexity"], "B": 8}
        without_graph = WORKFLOW.decide_plan(
            plan(parent="terra", complexity=complexity), roles=ROLES,
        )
        self.assertEqual(without_graph["classification"]["entry_tier"], "complex")
        self.assertEqual(without_graph["next_action"]["model"], "sol")

        with_graph = WORKFLOW.decide_plan(
            plan(parent="sol", complexity=complexity, graph=graph()), roles=ROLES,
        )
        self.assertEqual(with_graph["next_action"]["action"], "spawn")
        self.assertEqual(with_graph["next_action"]["model"], "terra")

    def test_ties_zero_and_bad_economics_fall_back_or_reject(self):
        economics = {
            "latency_weight": 0, "minimum_gain_ratio": 0,
            "single": {"cost_units": 0, "latency_ms": 0, "success_probability": 1},
            "dag": {"overhead_cost_units": 0, "overhead_latency_ms": 0, "success_probability": 1,
                    "tasks": {"a": {"cost_units": 0, "latency_ms": 0}, "b": {"cost_units": 0, "latency_ms": 0}}},
        }
        self.assertEqual(WORKFLOW.decide_plan(plan(graph=graph(), economics=economics), roles=ROLES)["execution_mode"], "single")
        economics["dag"]["tasks"].pop("b")
        with self.assertRaisesRegex(WORKFLOW.WorkflowError, "exactly match"):
            WORKFLOW.decide_plan(plan(graph=graph(), economics=economics), roles=ROLES)

    def test_overflow_is_invalid_in_api_and_cli(self):
        economics = {
            "latency_weight": 0, "minimum_gain_ratio": 0,
            "single": {"cost_units": 10 ** 400, "latency_ms": 0, "success_probability": 1},
            "dag": {"overhead_cost_units": 0, "overhead_latency_ms": 0, "success_probability": 1,
                    "tasks": {"a": {"cost_units": 0, "latency_ms": 0}, "b": {"cost_units": 0, "latency_ms": 0}}},
        }
        source = plan(graph=graph(), economics=economics)
        with self.assertRaisesRegex(WORKFLOW.WorkflowError, "finite"):
            WORKFLOW.decide_plan(source, roles=ROLES)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "plan", "--input", str(path)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")

    def test_strict_plan_and_after_implement_delegates_existing_escalation(self):
        with self.assertRaisesRegex(WORKFLOW.WorkflowError, "missing or unknown"):
            WORKFLOW.decide_plan({**plan(), "extra": True}, roles=ROLES)
        verification = {"schema": WORKFLOW.VERIFY_INPUT_SCHEMA, "parent": "parent", "available": ["sol", "terra"], "current_effort": "medium", "verifier": "fail", "delegation_available": True}
        output = WORKFLOW.decide_after_implement(verification, roles=ROLES)
        self.assertEqual(output["next_action"]["action"], "retry")
        self.assertEqual(output["next_action"]["model"], "terra")

    def test_workflow_defaults_to_inline_degrade_without_spawn_transport(self):
        source = plan(parent="sol")
        source.pop("delegation_available")
        output = WORKFLOW.decide_plan(source, roles=ROLES)
        self.assertEqual(output["next_action"]["status"], "degraded")
        self.assertEqual(output["next_action"]["action"], "parent")
        self.assertFalse(output["next_action"]["spawn"])

    def test_cli_plan_and_invalid_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(plan()), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "plan", "--input", str(path)], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["status"], "planned")
            path.write_text(json.dumps({"schema": WORKFLOW.PLAN_INPUT_SCHEMA}), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "plan", "--input", str(path)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
