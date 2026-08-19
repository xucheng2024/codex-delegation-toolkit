import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins/codex-delegation-toolkit"
ROUTER = (PLUGIN / "skills/cost-aware-routing/SKILL.md").read_text(encoding="utf-8")
BUDGET = (PLUGIN / "skills/agent-context-budget/SKILL.md").read_text(encoding="utf-8")
CAPSULE_LABELS = (
    "History scope:",
    "Budget tier:",
    "User request (verbatim):",
    "Objective:",
    "Deliverable:",
    "Scope:",
    "Anchors:",
    "Evidence:",
    "Parent hypothesis:",
    "Constraints/Risks:",
    "Acceptance:",
    "Retrieve/Escalate:",
)


class SkillContractTests(unittest.TestCase):
    def test_router_delegates_context_packaging_to_budget_skill(self):
        self.assertIn("invoke `$agent-context-budget`", ROUTER)
        self.assertIn("Do not invoke it when the task remains on the parent", ROUTER)

    def test_budget_does_not_select_routing(self):
        self.assertIn("Do not select the agent, model, or delegation strategy", BUDGET)

    def test_budget_retains_routine_and_expanded_soft_limits(self):
        for value in ("800 capsule tokens", "eight anchors", "1,500 capsule tokens", "twelve anchors", "not hard correctness limits"):
            self.assertIn(value, BUDGET)

    def test_router_does_not_claim_already_decided_handoffs(self):
        description = ROUTER.split("---", 2)[1]
        self.assertIn("decide whether or which model or subagent to use", description)
        self.assertIn("after routing is already decided", description)

    def test_capsule_has_each_label_once_and_in_order(self):
        block = re.search(r"```text\n(.*?)\n```", BUDGET, re.DOTALL)
        self.assertIsNotNone(block)
        positions = [block.group(1).index(label) for label in CAPSULE_LABELS]
        self.assertEqual(positions, sorted(positions))
        for label in CAPSULE_LABELS:
            self.assertEqual(block.group(1).count(label), 1)

    def test_skills_refer_to_current_accelerator(self):
        self.assertNotIn("$token-saver", ROUTER + BUDGET)
        self.assertIn("$codex-speeder", ROUTER)
        self.assertIn("$codex-speeder", BUDGET)

    def test_router_uses_durable_model_roles(self):
        for role in ("quality_first", "balanced", "economy"):
            self.assertIn(f"`{role}`", ROUTER)
        self.assertNotIn("Sol-class", ROUTER)
        self.assertNotIn("Terra-class", ROUTER)
        self.assertIn("scripts/resolve_model_roles.py", ROUTER)

    def test_router_spawn_contract_uses_explicit_model_ids(self):
        self.assertIn("model: gpt-5.6-sol", ROUTER)
        self.assertIn("model: gpt-5.6-terra", ROUTER)
        self.assertIn("Never omit `model` on `spawn_agent`", ROUTER)
        self.assertIn("Never inherit the parent model or `default_subagent_model`", ROUTER)
        self.assertNotIn("Keep implementation on the parent after planning", ROUTER)
        self.assertNotIn("keep capable work on the parent", ROUTER)

    def test_router_treats_stay_on_parent_as_ownership(self):
        self.assertIn("Staying on the parent assigns ownership of the decision and delivery, not who writes the code", ROUTER)
        self.assertIn("parent coordinates only; spawn a Terra executor", ROUTER)
        self.assertIn("Do not let an unpinned Sol parent run the long coding loop", ROUTER)

    def test_router_sol_pin_covers_all_work_unless_terra_delegation_is_permitted(self):
        self.assertIn(
            "An explicit user Sol pin applies to all task work unless the user explicitly permits delegation to Terra.",
            ROUTER,
        )
        self.assertIn("A runtime default, family alias, or leftover parent model is not a pin", ROUTER)
        self.assertIn("Sol pin without Terra-delegation permission: all slices stay on Sol, including implementation", ROUTER)

    def test_router_does_not_silently_swap_unavailable_models(self):
        self.assertIn("Do not silently substitute another model", ROUTER)
        self.assertIn("disclose the gap", ROUTER)
        self.assertIn("`available: false`, treat it as unavailable", ROUTER)
        self.assertIn("Do not fail closed to the parent for the entire task merely because a catalog file is missing", ROUTER)


if __name__ == "__main__":
    unittest.main()
