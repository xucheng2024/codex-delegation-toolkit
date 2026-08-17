import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
SKILLS = ("cost-aware-routing", "agent-context-budget")


class PackageTests(unittest.TestCase):
    def test_plugin_manifest_is_complete(self):
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "codex-delegation-toolkit")
        self.assertEqual(manifest["skills"], "./skills/")
        for field in ("version", "description", "author", "repository", "license", "interface"):
            self.assertIn(field, manifest)

    def test_skill_frontmatter_and_ui_metadata(self):
        for name in SKILLS:
            text = (ROOT / f"skills/{name}/SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("[TODO:", text)
            _, frontmatter, _ = text.split("---", 2)
            metadata = yaml.safe_load(frontmatter)
            self.assertEqual(metadata["name"], name)
            self.assertTrue(metadata["description"])

            agent = yaml.safe_load((ROOT / f"skills/{name}/agents/openai.yaml").read_text(encoding="utf-8"))
            self.assertIn("interface", agent)
            self.assertIn(f"${name}", agent["interface"]["default_prompt"])


if __name__ == "__main__":
    unittest.main()
