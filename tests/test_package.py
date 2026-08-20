import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins/codex-delegation-toolkit"
SKILLS = ("cost-aware-routing", "agent-context-budget")


class PackageTests(unittest.TestCase):
    def test_plugin_manifest_is_complete(self):
        manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "codex-delegation-toolkit")
        self.assertEqual(manifest["skills"], "./skills/")
        for field in ("version", "description", "author", "repository", "license", "interface"):
            self.assertIn(field, manifest)

    def test_skill_frontmatter_and_ui_metadata(self):
        for name in SKILLS:
            text = (PLUGIN / f"skills/{name}/SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("[TODO:", text)
            _, frontmatter, _ = text.split("---", 2)
            metadata = yaml.safe_load(frontmatter)
            self.assertEqual(metadata["name"], name)
            self.assertTrue(metadata["description"])

            agent = yaml.safe_load((PLUGIN / f"skills/{name}/agents/openai.yaml").read_text(encoding="utf-8"))
            self.assertIn("interface", agent)
            self.assertIn(f"${name}", agent["interface"]["default_prompt"])

    def test_marketplace_points_to_the_plugin(self):
        marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        names = [entry["name"] for entry in marketplace["plugins"]]
        self.assertEqual(names[0], "codex-delegation-toolkit")
        self.assertIn("keep-plot", names)
        by_name = {entry["name"]: entry for entry in marketplace["plugins"]}
        toolkit = by_name["codex-delegation-toolkit"]
        self.assertEqual(toolkit["source"]["path"], "./plugins/codex-delegation-toolkit")
        self.assertTrue((ROOT / toolkit["source"]["path"] / ".codex-plugin/plugin.json").is_file())
        keep_plot = by_name["keep-plot"]
        self.assertEqual(keep_plot["source"]["path"], "./plugins/keep-plot")
        self.assertTrue((ROOT / keep_plot["source"]["path"] / ".codex-plugin/plugin.json").is_file())

    def test_toolkit_plugin_does_not_include_same_thread_checkpoint(self):
        self.assertEqual(SKILLS, ("cost-aware-routing", "agent-context-budget"))
        self.assertFalse((PLUGIN / "skills/keep-plot").exists())
        self.assertFalse((PLUGIN / "skills/context-checkpoint").exists())
        skill_dirs = sorted(path.name for path in (PLUGIN / "skills").iterdir() if path.is_dir())
        self.assertEqual(skill_dirs, sorted(SKILLS))


if __name__ == "__main__":
    unittest.main()
