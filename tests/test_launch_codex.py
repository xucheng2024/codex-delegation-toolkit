import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/codex-delegation-toolkit/skills/cost-aware-routing/scripts/launch_codex.py"
SPEC = importlib.util.spec_from_file_location("launch_codex", SCRIPT)
LAUNCHER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(LAUNCHER)


class LaunchCodexTests(unittest.TestCase):
    def test_extracts_available_models_from_catalog(self):
        self.assertEqual(
            LAUNCHER.available_models({"models": [{"slug": "luna"}, {"slug": "terra"}]}),
            {"luna", "terra"},
        )

    def test_rejects_invalid_or_empty_catalog(self):
        for catalog in ({}, {"models": []}, {"models": [{"name": "terra"}]}):
            with self.subTest(catalog=catalog), self.assertRaises(LAUNCHER.LaunchError):
                LAUNCHER.available_models(catalog)

    def test_command_pins_selected_model_and_effort_before_first_call(self):
        selection = {"status": "selected", "model": "luna", "effort": "medium"}
        command = LAUNCHER.build_codex_command(
            "codex", selection, ["--", "--ephemeral", "--sandbox", "workspace-write"]
        )
        self.assertEqual(
            command,
            [
                "codex", "exec", "-m", "luna", "-c",
                'model_reasoning_effort="medium"', "--ephemeral", "--sandbox",
                "workspace-write", "-",
            ],
        )

    def test_rejects_model_override_and_noninitial_subcommands(self):
        selection = {"status": "selected", "model": "luna", "effort": "medium"}
        for args in (
            ["--model", "terra"],
            ["-c", "model=\"terra\""],
            ["--config=model_reasoning_effort=high"],
            ["resume", "--last"],
        ):
            with self.subTest(args=args), self.assertRaises(LAUNCHER.LaunchError):
                LAUNCHER.build_codex_command("codex", selection, args)

    def test_routing_receipt_prevents_duplicate_skill_routing(self):
        selection = {
            "status": "selected",
            "model": "luna",
            "effort": "medium",
            "role": "economy",
            "classification": {"entry_tier": "fast"},
        }
        prompt = LAUNCHER.routed_prompt("Fix the parser.", selection)
        self.assertIn("ENTRY_ROUTING_COMPLETE", prompt)
        self.assertIn("Do not invoke cost-aware-routing again", prompt)
        self.assertTrue(prompt.endswith("Fix the parser."))

    def test_select_only_does_not_start_codex(self):
        catalog = {"models": [{"slug": "gpt-5.6-luna"}]}
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "models.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "--A", "1", "--B", "0", "--U", "0",
                    "--preflight-complete", "--catalog-file", str(catalog_path), "--select-only",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["model"], "gpt-5.6-luna")

    def test_launches_once_with_receipt_on_stdin(self):
        argv = [
            "--A", "1", "--B", "0", "--U", "0", "--preflight-complete",
            "--available", "gpt-5.6-luna", "--prompt", "Fix it.", "--", "--ephemeral",
        ]
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.object(LAUNCHER.subprocess, "run", return_value=completed) as run:
            self.assertEqual(LAUNCHER.main(argv), 0)
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["codex", "exec", "-m", "gpt-5.6-luna"])
        self.assertIn("ENTRY_ROUTING_COMPLETE", run.call_args.kwargs["input"])


if __name__ == "__main__":
    unittest.main()
