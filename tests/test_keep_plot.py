import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
TOOLKIT = ROOT / "plugins/codex-delegation-toolkit"
PLUGIN = ROOT / "plugins/keep-plot"
SKILL = PLUGIN / "skills/keep-plot"


class KeepPlotTests(unittest.TestCase):
    def test_lives_outside_the_toolkit_plugin(self):
        self.assertTrue((PLUGIN / ".codex-plugin/plugin.json").is_file())
        self.assertFalse((TOOLKIT / "skills/keep-plot").exists())

    def test_skill_is_explicit_only_and_out_of_scope_for_speeder_and_handoffs(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("[TODO:", text)
        _, frontmatter, body = text.split("---", 2)
        metadata = yaml.safe_load(frontmatter)
        self.assertEqual(metadata["name"], "keep-plot")
        description = metadata["description"]
        self.assertIn("$keep-plot", description)
        self.assertIn("without losing the plot", description)
        self.assertIn("$codex-speeder", description)
        self.assertIn("$agent-context-budget", description)
        self.assertIn("Do not auto-trigger on token percent", description)
        self.assertLessEqual(len(description), 1024)
        self.assertNotIn("<", description)
        self.assertNotIn(">", description)

        for value in (
            "Compact at semantic boundaries",
            "does not call `/compact`",
            "Do not rescan the repository",
            "obsolete ratio",
            "CURRENT OBJECTIVE",
            "SAFETY INVARIANTS",
            "What is the current objective?",
            "Do not continue blind",
            "Do not invoke `$agent-context-budget` or `$codex-speeder`",
            "↳ Keep Plot:",
            "record_outcome.py",
            "references/percent-bands.md",
        ):
            self.assertIn(value, body)
        skill_lines = text.count("\n") + (0 if text.endswith("\n") else 1)
        self.assertGreaterEqual(skill_lines, 80)
        self.assertLessEqual(skill_lines, 150)
        self.assertTrue((SKILL / "references/percent-bands.md").is_file())

        agent = yaml.safe_load((SKILL / "agents/openai.yaml").read_text(encoding="utf-8"))
        self.assertFalse(agent["policy"]["allow_implicit_invocation"])
        self.assertIn("$keep-plot", agent["interface"]["default_prompt"])
        self.assertEqual(agent["interface"]["display_name"], "Keep Plot")
        self.assertGreaterEqual(len(agent["interface"]["short_description"]), 25)
        self.assertLessEqual(len(agent["interface"]["short_description"]), 64)

    def test_plugin_manifest_is_complete(self):
        manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "keep-plot")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertIn("$keep-plot", manifest["interface"]["defaultPrompt"])
        self.assertEqual(manifest["interface"]["displayName"], "Keep Plot")
        self.assertTrue(manifest["interface"]["capabilities"])

    def test_record_outcome_counts_current_repo_only(self):
        spec = importlib.util.spec_from_file_location(
            "record_outcome",
            SKILL / "scripts/record_outcome.py",
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["KEEP_PLOT_CACHE_DIR"] = temp_dir
            try:
                module.record("compact", "phase closed", "na")
                module.record("restore", "missing next step", "fail")
                stats = module.format_stats(module.load_records())
            finally:
                os.environ.pop("KEEP_PLOT_CACHE_DIR", None)
        self.assertIn("compact=1", stats)
        self.assertIn("restore=1", stats)
        self.assertIn("post_check pass=0 fail=1", stats)
        self.assertNotIn("phase closed", stats)


if __name__ == "__main__":
    unittest.main()
