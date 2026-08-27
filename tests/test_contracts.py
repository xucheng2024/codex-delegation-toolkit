import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins/codex-delegation-toolkit"
ROUTER = (PLUGIN / "skills/cost-aware-routing/SKILL.md").read_text(encoding="utf-8")
REVIEWED = (PLUGIN / "skills/cost-aware-routing/references/reviewed-workflow.md").read_text(encoding="utf-8")
ROUTING_CONTRACT = ROUTER + "\n" + REVIEWED
WORKFLOW_ECONOMICS = (PLUGIN / "skills/cost-aware-routing/references/workflow-economics.md").read_text(encoding="utf-8")
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
        self.assertIn("invoke `$agent-context-budget`", ROUTING_CONTRACT)
        self.assertIn("do not invoke it when work remains on the parent", ROUTING_CONTRACT)
        self.assertIn("If action is `parent`, do not invoke `$agent-context-budget`", ROUTING_CONTRACT)
        self.assertIn("do not render an execute capsule", ROUTING_CONTRACT)
        self.assertIn("keep only `STATUS` plus the contract or `FINDINGS`", ROUTING_CONTRACT)

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
            "ordinarily judges locally", "--independent-review",
            "fresh read-only `quality_first` reviewer",
            "`plan-review` is a distinct pre-implementation gate",
            "always spawns a fresh read-only `quality_first` reviewer",
            "never silently substitute a model",
            "presence of `wait` alone is not delegation capability",
            "If it does not, pass the literal `current`; never guess a role or model id",
        ):
            self.assertIn(value, ROUTING_CONTRACT)

    def test_router_bounds_delegation_waits_and_requires_a_spawn_handle(self):
        for value in (
            "Treat a route decision as intent, never as proof that a child exists",
            "Never call `wait_agent` unless that call returned a non-empty identifier",
            "an empty receiver set is an immediate transport failure",
            "make at most two `wait_agent` calls of at most 60 seconds each",
            "interrupt that identifier once",
            "Do not retry spawn",
        ):
            self.assertIn(value, ROUTING_CONTRACT)

    def test_router_uses_verifier_gated_escalation(self):
        for value in (
            "scripts/escalate_step.py",
            "Do not use self-reported confidence",
            "First-pass `route_step` effort is always `medium`",
            "scripts/record_compute.py",
            "Terra applies findings once and stops",
            "do not run `escalate_step.py` again",
        ):
            self.assertIn(value, ROUTING_CONTRACT)

    def test_router_keeps_independent_review_gate(self):
        for value in (
            "After a Sol-planned or `--sol-pin` path",
            "Terra-only simple work: Terra reviews its own diff",
            "material correctness, security, compatibility, or contract risk",
            "focused caller/configuration/test impact references",
            "never resume the planner",
        ):
            self.assertIn(value, ROUTING_CONTRACT)

    def test_router_classifies_before_read_and_keeps_sol_from_editing(self):
        for value in (
            "bounded read-only one-hop impact preflight",
            "Use `entry_tier` for workflow shape and first-model selection",
            "use `effective_tier` only for implementation-role compatibility",
            "Permissions and authorization are separate execution constraints, never score inputs",
            "Effective `fast`",
            "Entry `complex`",
            "Sol never edits",
            "It forces Sol plan plus review; it does not make Sol implement",
            "from the approved contract with no second plan",
            "pause for explicit user approval after plan review",
            "Decorative equations are forbidden",
            "The Sol planner is read-only and may inspect the repo",
            "writes anchors, scope, and acceptance",
        ):
            self.assertIn(value, ROUTING_CONTRACT)

    def test_spawned_sol_loads_matching_skills_independently(self):
        for value in (
            "Each spawned Sol agent must independently discover/load any skill whose trigger matches its task",
            "Do not assume parent skill context is inherited",
            "Do not re-invoke `$cost-aware-routing` or `$agent-context-budget`",
        ):
            self.assertIn(value, ROUTING_CONTRACT)
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
        self.assertIn("[references/handoff-output.md]", ROUTER)
        self.assertIn("STATUS: APPROVE | CHANGES_REQUIRED | INCOMPLETE", ROUTING_CONTRACT)
        self.assertIn("`FINDINGS`, `VALIDATION`, and `OVERFLOW_REASON`", ROUTING_CONTRACT)
        for value in (
            "soft ceiling", "OVERFLOW_REASON", "receiver must stop", "Share references, not duplicated context",
            "impact × uncertainty × actionability", "ordering heuristic",
        ):
            self.assertIn(value, HANDOFF)

    def test_router_requires_canonical_cache_prefix(self):
        for value in (
            "scripts/render_cache_handoff.py", "CACHE_HANDOFF_V1", "byte-identical",
            "DYNAMIC_PACKET_JSON", "encode its non-empty fields as one JSON object",
            "append a delta message or `codex queue`", "do not rewrite the original packet",
            "do not respawn", "do not rebuild the capsule",
            "Do not pad the prefix with filler",
            'Keep `fork_turns: "none"`',
            "alternate approach",
        ):
            self.assertIn(value, ROUTING_CONTRACT)

    def test_budget_omits_inapplicable_fields_and_appends_deltas(self):
        self.assertIn("Omit inapplicable fields", BUDGET)
        self.assertNotIn("Fill every field", BUDGET)
        self.assertNotIn("None — independent review of the diff only", BUDGET)
        self.assertIn("Send only Scope, Constraints/Risks, Acceptance, and Anchors", BUDGET)
        self.assertIn("If the diff text is already in the packet, do not invoke `$codex-speeder`", BUDGET)
        self.assertIn("The reviewer still independently loads matching task skills", BUDGET)
        self.assertIn("Pre-exploration **plan** packets", BUDGET)
        self.assertIn("**execute** packets are only for a spawned implementer", BUDGET)
        self.assertIn("do not build an execute packet", BUDGET)
        self.assertIn("Omit parent-invented Scope, Anchors, Evidence, and Acceptance", BUDGET)
        self.assertIn("Do not assume parent skill context is inherited", BUDGET)
        self.assertIn("Keep the original packet message and append the delta", BUDGET)
        self.assertIn("do not rewrite the first packet", BUDGET)
        self.assertIn("A same-child `codex queue` message is a delta, not a new capsule", BUDGET)
        self.assertIn("short new instruction, not a rebuilt capsule", BUDGET)
        self.assertIn('Use `fork_turns: "none"`', BUDGET)

    def test_handoff_later_rounds_append(self):
        self.assertIn("keep the original packet and append", HANDOFF)
        self.assertIn("Do not rewrite the first packet", HANDOFF)

    def test_router_still_refers_to_current_accelerator(self):
        self.assertNotIn("$token-saver", ROUTER + BUDGET + HANDOFF)
        self.assertIn("$codex-speeder", ROUTER)

    def test_router_has_a_bounded_low_overhead_fast_path(self):
        self.assertLess(len(ROUTER.encode("utf-8")), 7000)
        for value in (
            "Do not repeat repository searches",
            "Do not run a tool's `capabilities` or `--help`",
            "Preserve successful legacy behavior before adding a fallback",
            "Python `bool` being an `int`",
            "run the smallest focused deterministic validation",
            "Do not rerun passed checks unless files change",
            "Only on `fail` or `incomplete`",
            "Do not load the reviewed-workflow",
        ):
            self.assertIn(value, ROUTER)

    def test_router_documents_deterministic_task_graph_completion(self):
        reference = (PLUGIN / "skills/cost-aware-routing/references/task-graph.md").read_text(encoding="utf-8")
        for value in (
            "schedule_task_graph.py", "mandatory integration validation and then a `judge`",
            "--allow-recursive-delegation", "deterministic dependency-aware waves",
            "different functions in the same file remain serial by default",
        ):
            self.assertIn(value, ROUTING_CONTRACT)
        for value in ("sorted Kahn ready sets", "ancestor/descendant paths conflict", "integration_validation"):
            self.assertIn(value, reference)

    def test_router_selects_entry_model_before_first_model_call(self):
        for value in (
            "scripts/select_entry_model.py",
            "before the first model call",
            "selector is deterministic and invokes no model",
            "fast` classification selects Luna at medium effort",
            "standard` selects Terra at medium effort",
            "complex` selects Sol to plan",
            "Entry selection does not enable parallelism",
        ):
            self.assertIn(value, ROUTER)

    def test_router_exposes_pre_model_launcher_without_implicit_loading(self):
        metadata = (PLUGIN / "skills/cost-aware-routing/agents/openai.yaml").read_text(encoding="utf-8")
        launcher = PLUGIN / "skills/cost-aware-routing/scripts/launch_codex.py"
        self.assertTrue(launcher.is_file())
        self.assertIn("scripts/launch_codex.py", ROUTER)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("routing receipt that prevents duplicate routing", ROUTER)

    def test_router_documents_workflow_economics_and_measurement(self):
        self.assertIn("references/workflow-economics.md", ROUTER)
        self.assertIn(
            "For one bounded task with no proposed graph and no supplied economics",
            ROUTER,
        )
        self.assertIn("route it directly with `route_step.py`", ROUTER)
        self.assertIn("do not read the workflow-economics reference", ROUTER)
        for value in (
            "scripts/orchestrate_workflow.py", "scripts/record_compute.py record-workflow",
            "required reducer use order", "conservative fallback",
            "approved supplied graph proceeds to implementation and is never planned again",
        ):
            self.assertIn(value, ROUTING_CONTRACT)
        for value in (
            "expected_score = (K + latency_weight * L) / p",
            "K = dag.overhead_cost_units + sum(task.cost_units)",
            "L = dag.overhead_latency_ms + sum(max(task.latency_ms in wave) for wave)",
            "status `insufficient`", "partial or mismatched estimates", "rejected rather than guessed",
            "Gather bounded preflight evidence", "obtain an approved graph",
            "Invoke `orchestrate_workflow.py plan` once", "internally classifies and schedules",
            "supplied graph is already approved",
            "execution_mode` and `next_action`", "orchestrate_workflow.py\n   after-implement",
            "codex-workflow-outcome-v1", "record_compute.py record-workflow",
        ):
            self.assertIn(value, WORKFLOW_ECONOMICS)

    def test_cache_prefix_eval_uses_renderer_and_cache_fields(self):
        eval_source = (ROOT / "experiments/cache_prefix_eval.py").read_text(encoding="utf-8")
        self.assertIn("load_renderer", eval_source)
        self.assertIn("render_packet", eval_source)
        self.assertIn("cache_usage", eval_source)
        self.assertNotIn("PREFIX =", eval_source)


if __name__ == "__main__":
    unittest.main()
