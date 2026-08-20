import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/render_cache_handoff.py"


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_cache_handoff", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CacheHandoffTests(unittest.TestCase):
    def test_same_kind_has_identical_prefix_and_dynamic_suffix(self):
        renderer = load_renderer()
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.txt"
            second = Path(directory) / "second.txt"
            first.write_text('{"scope":"one","objective":"review"}', encoding="utf-8")
            second.write_text('{ "objective": "review", "scope": "two" }', encoding="utf-8")
            one = renderer.render("review", first)
            two = renderer.render("review", second)
        prefix = renderer.PREFIXES["review"]
        self.assertTrue(one.startswith(prefix))
        self.assertTrue(two.startswith(prefix))
        self.assertEqual(one[: len(prefix)], two[: len(prefix)])
        self.assertEqual(one[len(prefix):], '{"objective":"review","scope":"one"}\n')
        self.assertEqual(two[len(prefix):], '{"objective":"review","scope":"two"}\n')

    def test_empty_dynamic_packet_fails_closed(self):
        renderer = load_renderer()
        with tempfile.TemporaryDirectory() as directory:
            dynamic = Path(directory) / "empty.txt"
            dynamic.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                renderer.render("review", dynamic)

    def test_invalid_dynamic_packet_fails_closed(self):
        renderer = load_renderer()
        with tempfile.TemporaryDirectory() as directory:
            dynamic = Path(directory) / "invalid.txt"
            dynamic.write_text("not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                renderer.render("review", dynamic)

    def test_plan_and_execute_prefixes_stay_short_with_result_schema(self):
        renderer = load_renderer()
        plan = renderer.PREFIXES["plan"]
        execute = renderer.PREFIXES["execute"]
        self.assertTrue(plan.startswith("CACHE_HANDOFF_V1\nKIND: PLAN\n"))
        self.assertTrue(execute.startswith("CACHE_HANDOFF_V1\nKIND: EXECUTE\n"))
        self.assertIn("CONTRACT: Objective, Scope, Constraints/Risks, Acceptance, Retrieve/Escalate; name gaps.", plan)
        self.assertIn("VALIDATION: focused checks; stop rather than widen or guess.", execute)
        self.assertIn("If the diff is in the packet, do not use tools or other skills", renderer.PREFIXES["review"])
        self.assertLess(len(renderer.PREFIXES["review"]), 800)

    def test_render_packet_matches_file_render(self):
        renderer = load_renderer()
        with tempfile.TemporaryDirectory() as directory:
            dynamic = Path(directory) / "packet.json"
            dynamic.write_text('{"scope":"one"}', encoding="utf-8")
            self.assertEqual(renderer.render("plan", dynamic), renderer.render_packet("plan", {"scope": "one"}))

    def test_dump_strips_none_filler_and_empty_values(self):
        renderer = load_renderer()
        packet = {
            "scope": "app/auth.py",
            "objective": "None — independent review of the diff only",
            "deliverable": "",
            "evidence": None,
            "anchors": "diff --git a/app/auth.py",
        }
        rendered = renderer.render_packet("review", packet)
        suffix = rendered[len(renderer.PREFIXES["review"]):]
        self.assertEqual(suffix, '{"anchors":"diff --git a/app/auth.py","scope":"app/auth.py"}\n')
