import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins/codex-delegation-toolkit"
ROUTER = (PLUGIN / "skills/cost-aware-routing/SKILL.md").read_text(encoding="utf-8")
HANDOFF = (PLUGIN / "skills/cost-aware-routing/references/handoff-output.md").read_text(encoding="utf-8")
BUDGET = (PLUGIN / "skills/agent-context-budget/SKILL.md").read_text(encoding="utf-8")
CAPSULE_LABELS = (
    "History scope:", "Budget tier:", "User request (verbatim):", "Objective:",
    "Deliverable:", "Scope:", "Anchors:", "Evidence:", "Parent hypothesis:",
    "Constraints/Risks:", "Acceptance:", "Retrieve/Escalate:",
)


class SkillContractTests(unittest.TestCase):
    def test_router_metadata_and_context_boundary(self):
        description = ROUTER.split("---", 2)[1]
        self.assertIn("explicit model/delegation decisions", description)
        self.assertIn("after routing is decided", description)
        self.assertIn("invoke `$agent-context-budget`", ROUTER)
        self.assertIn("do not invoke it when work remains on the parent", ROUTER)

    def test_budget_contract_is_stable(self):
        self.assertIn("Do not select the agent, model, or delegation strategy", BUDGET)
        block = re.search(r"```text\n(.*?)\n```", BUDGET, re.DOTALL)
        self.assertIsNotNone(block)
        positions = [block.group(1).index(label) for label in CAPSULE_LABELS]
        self.assertEqual(positions, sorted(positions))

    def test_router_keeps_safety_critical_routing_rules(self):
        for value in (
            "`quality_first`", "`balanced`", "scripts/route_step.py",
            "Honor the script output", "do not re-derive the matrix",
            "fresh spawned `quality_first` instance",
            "never silently substitute a model",
        ):
            self.assertIn(value, ROUTER)

    def test_router_keeps_independent_review_gate(self):
        for value in (
            "After any non-Sol hard-trigger implementation",
            "complete contract, no material deviation, and passing deterministic validation",
            "material correctness, security, compatibility, or contract risk",
            "focused caller/configuration/test impact references",
        ):
            self.assertIn(value, ROUTER)

    def test_handoff_reference_is_conditional_and_safe(self):
        self.assertIn("Read [references/handoff-output.md]", ROUTER)
        self.assertIn("STATUS: APPROVE | CHANGES_REQUIRED | INCOMPLETE", ROUTER)
        self.assertIn("FINDINGS`, `VALIDATION`, and `OVERFLOW_REASON`", ROUTER)
        for value in (
            "soft ceiling", "OVERFLOW_REASON", "receiver must stop", "Share references, not duplicated context",
            "impact × uncertainty × actionability", "ordering heuristic",
        ):
            self.assertIn(value, HANDOFF)

    def test_router_requires_canonical_cache_prefix(self):
        for value in (
            "scripts/render_cache_handoff.py", "CACHE_HANDOFF_V1", "byte-identical",
            "DYNAMIC_PACKET_JSON", "encode its non-empty fields as one JSON object",
        ):
            self.assertIn(value, ROUTER)

    def test_router_still_refers_to_current_accelerator(self):
        self.assertNotIn("$token-saver", ROUTER + BUDGET + HANDOFF)
        self.assertIn("$codex-speeder", ROUTER)


if __name__ == "__main__":
    unittest.main()
