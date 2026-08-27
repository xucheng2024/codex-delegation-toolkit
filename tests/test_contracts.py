import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins/codex-delegation-toolkit"
ROUTER = (PLUGIN / "skills/cost-aware-routing/SKILL.md").read_text(encoding="utf-8")
REVIEWED = (PLUGIN / "skills/cost-aware-routing/references/reviewed-workflow.md").read_text(encoding="utf-8")
ROUTING_CONTRACT = ROUTER + "\n" + REVIEWED
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
        self.assertIn("invoke `$codex-delegation-toolkit:agent-context-budget`", ROUTING_CONTRACT)
        self.assertIn("do not invoke it when work remains on the parent", ROUTING_CONTRACT)
        self.assertIn("If action is `parent`, do not invoke `$codex-delegation-toolkit:agent-context-budget`", ROUTING_CONTRACT)
        self.assertIn("do not render an execute capsule", ROUTING_CONTRACT)
        self.assertIn("Keep only `STATUS` plus the task graph or `FINDINGS`", ROUTING_CONTRACT)

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
            "quality-first parent judges the final diff locally",
            "Sol decomposes complex work",
            "Do not spawn a separate judge",
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
            "resolve the repository root with `pwd -P`",
            "repository-relative owned paths",
            "only after its declared diff and deterministic validation are visible",
        ):
            self.assertIn(value, ROUTING_CONTRACT)

    def test_router_uses_verifier_gated_escalation(self):
        for value in (
            "scripts/escalate_step.py",
            "Do not use self-reported confidence",
            "First-pass `route_step` effort is always `medium`",
            "Terra applies findings once and stops",
            "do not run `escalate_step.py` again",
        ):
            self.assertIn(value, ROUTING_CONTRACT)

    def test_router_keeps_final_review_gate(self):
        for value in (
            "After a Sol-decomposed or `--sol-pin` path",
            "Terra-only simple work: Terra reviews its own diff",
            "material correctness, security, compatibility, contract risk",
            "focused caller/configuration/test impact references",
            "Do not spawn a separate judge",
        ):
            self.assertIn(value, ROUTING_CONTRACT)

    def test_router_classifies_before_read_and_keeps_sol_from_editing(self):
        for value in (
            "bounded read-only one-hop impact preflight",
            "Use `entry_tier` for workflow shape and first-model selection",
            "use `effective_tier` only for implementation-role compatibility",
            "Permissions and authorization are separate execution constraints, never score inputs",
            "`complex`",
            "Sol never edits",
            "It forces the Sol decomposition queue; it does not make Sol implement",
            "Sol decomposes the work into a bounded task graph",
        ):
            self.assertIn(value, ROUTING_CONTRACT)

    def test_spawned_sol_loads_matching_skills_independently(self):
        for value in (
            "Each spawned Sol agent must independently discover/load any skill whose trigger matches its task",
            "Do not assume parent skill context is inherited",
            "Do not re-invoke `$codex-delegation-toolkit:cost-aware-routing` or `$codex-delegation-toolkit:agent-context-budget`",
        ):
            self.assertIn(value, ROUTING_CONTRACT)
        for value in (
            "Independently load matching task skills; do not assume parent skill context is inherited",
            "Do not invoke $codex-delegation-toolkit:cost-aware-routing or $codex-delegation-toolkit:agent-context-budget",
        ):
            self.assertIn(value, RENDERER.PREFIXES["decompose"])
        review = RENDERER.PREFIXES["review"]
        self.assertIn("Fresh review: no planner context", review)
        self.assertIn("Independently load matching task skills", review)
        self.assertIn("Do not invoke $codex-delegation-toolkit:cost-aware-routing, $codex-delegation-toolkit:agent-context-budget, or $codex-speeder:codex-speeder", review)
        self.assertNotIn("do not use tools or other skills", review)
        self.assertIn("Do not re-decompose. Retrieve named anchors first.", RENDERER.PREFIXES["execute"])

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
        self.assertIn("Pre-exploration **decompose** packets", BUDGET)
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
            "complex` selects Sol to decompose",
            "Entry selection does not enable parallelism",
            "must not spawn merely to downgrade cost",
        ):
            self.assertIn(value, ROUTER)

    def test_router_exposes_pre_model_launcher_and_implicit_discovery(self):
        metadata = (PLUGIN / "skills/cost-aware-routing/agents/openai.yaml").read_text(encoding="utf-8")
        launcher = PLUGIN / "skills/cost-aware-routing/scripts/launch_codex.py"
        self.assertTrue(launcher.is_file())
        self.assertIn("scripts/launch_codex.py", ROUTER)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("routing receipt that prevents duplicate routing", ROUTER)

    def test_router_documents_three_queue_dispatch(self):
        for value in (
            "Every task enters one queue", "`fast` for `economy` (Luna)",
            "`standard` for `balanced` (Terra)", "`complex` for `quality_first` (Sol)",
            "run `scripts/orchestrate_workflow.py`", "without another planning or economics pass",
            "exactly one logical owner", "do not create queues, owners, or implementation agents",
            "Execute every queue and dependency wave serially", "stop its dependents",
        ):
            self.assertIn(value, ROUTING_CONTRACT)
        self.assertNotIn("workflow-economics", ROUTING_CONTRACT)

    def test_cache_prefix_eval_uses_renderer_and_cache_fields(self):
        eval_source = (ROOT / "experiments/cache_prefix_eval.py").read_text(encoding="utf-8")
        self.assertIn("load_renderer", eval_source)
        self.assertIn("render_packet", eval_source)
        self.assertIn("cache_usage", eval_source)
        self.assertNotIn("PREFIX =", eval_source)


if __name__ == "__main__":
    unittest.main()
