import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins/codex-delegation-toolkit"
ROUTER = (PLUGIN / "skills/cost-aware-routing/SKILL.md").read_text(encoding="utf-8")
HANDOFF = (PLUGIN / "skills/cost-aware-routing/references/handoff-output.md").read_text(encoding="utf-8")
BUDGET = (PLUGIN / "skills/agent-context-budget/SKILL.md").read_text(encoding="utf-8")
RENDERER_PATH = PLUGIN / "skills/cost-aware-routing/scripts/render_cache_handoff.py"
_SPEC = importlib.util.spec_from_file_location("render_cache_handoff", RENDERER_PATH)
RENDERER = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(RENDERER)
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
        self.assertIn("Do not use for ordinary single-agent work", BUDGET)
        self.assertNotIn("keep-plot", BUDGET)
        self.assertNotIn("$keep-plot", ROUTER)
        self.assertNotIn("context-checkpoint", BUDGET)
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
            "After a Sol-planned or `--sol-pin` path",
            "Terra-only simple work: Terra reviews its own diff",
            "material correctness, security, compatibility, or contract risk",
            "focused caller/configuration/test impact references",
            "never resume the planner",
        ):
            self.assertIn(value, ROUTER)

    def test_router_classifies_before_read_and_keeps_sol_from_editing(self):
        for value in (
            "Classify from the user request only",
            "Do not read the repo, search, or draft a plan before the routing decision",
            "Sol never edits",
            "It forces Sol plan plus review; it does not make Sol implement",
            "from the approved contract with no second plan",
            "The Sol planner is read-only and may inspect the repo",
            "writes anchors, scope, and acceptance",
        ):
            self.assertIn(value, ROUTER)

    def test_spawned_sol_loads_matching_skills_independently(self):
        for value in (
            "Each spawned Sol agent must independently discover/load any skill whose trigger matches its task",
            "Do not assume parent skill context is inherited",
            "Do not re-invoke `$cost-aware-routing` or `$agent-context-budget`",
        ):
            self.assertIn(value, ROUTER)
        for value in (
            "Independently load matching task skills; do not assume parent skill context is inherited",
            "Do not invoke $cost-aware-routing or $agent-context-budget",
        ):
            self.assertIn(value, RENDERER.PREFIXES["plan"])
        review = RENDERER.PREFIXES["review"]
        self.assertIn("Fresh review: no planner context", review)
        self.assertIn("Independently load matching task skills", review)
        self.assertIn("Do not invoke $cost-aware-routing, $agent-context-budget, or $codex-speeder", review)
        self.assertNotIn("do not use tools or other skills", review)
        self.assertIn("Do not re-plan. Retrieve named anchors first.", RENDERER.PREFIXES["execute"])

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
            "append a delta message", "do not rewrite the original packet",
            "Do not pad the prefix with filler",
        ):
            self.assertIn(value, ROUTER)

    def test_budget_omits_inapplicable_fields_and_appends_deltas(self):
        self.assertIn("Omit inapplicable fields", BUDGET)
        self.assertNotIn("Fill every field", BUDGET)
        self.assertNotIn("None — independent review of the diff only", BUDGET)
        self.assertIn("Send only Scope, Constraints/Risks, Acceptance, and Anchors", BUDGET)
        self.assertIn("If the diff text is already in the packet, do not invoke `$codex-speeder`", BUDGET)
        self.assertIn("The reviewer still independently loads matching task skills", BUDGET)
        self.assertIn("Pre-exploration **plan** packets", BUDGET)
        self.assertIn("Omit parent-invented Scope, Anchors, Evidence, and Acceptance", BUDGET)
        self.assertIn("Do not assume parent skill context is inherited", BUDGET)
        self.assertIn("Keep the original packet message and append the delta", BUDGET)
        self.assertIn("do not rewrite the first packet", BUDGET)

    def test_handoff_later_rounds_append(self):
        self.assertIn("keep the original packet and append", HANDOFF)
        self.assertIn("Do not rewrite the first packet", HANDOFF)

    def test_router_still_refers_to_current_accelerator(self):
        self.assertNotIn("$token-saver", ROUTER + BUDGET + HANDOFF)
        self.assertIn("$codex-speeder", ROUTER)

    def test_cache_prefix_eval_uses_renderer_and_cache_fields(self):
        eval_source = (ROOT / "experiments/cache_prefix_eval.py").read_text(encoding="utf-8")
        self.assertIn("load_renderer", eval_source)
        self.assertIn("render_packet", eval_source)
        self.assertIn("cache_usage", eval_source)
        self.assertNotIn("PREFIX =", eval_source)


if __name__ == "__main__":
    unittest.main()
