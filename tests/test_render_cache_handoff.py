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
