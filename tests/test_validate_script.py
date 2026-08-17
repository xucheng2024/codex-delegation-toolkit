import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/validate"
LOADER = importlib.machinery.SourceFileLoader("validate_script", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
VALIDATE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VALIDATE)


class ValidateScriptTests(unittest.TestCase):
    def test_fingerprint_tracks_complete_requirements_file(self):
        first = VALIDATE.requirements_fingerprint()
        second = VALIDATE.requirements_fingerprint()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_environment_changes_with_any_dependency_change(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            requirements = Path(temp_dir) / "requirements-dev.txt"
            requirements.write_text("first-package==1.0\n", encoding="utf-8")
            with mock.patch.object(VALIDATE, "REQUIREMENTS", requirements):
                first = VALIDATE.environment_path()
                requirements.write_text("second-package==2.0\n", encoding="utf-8")
                second = VALIDATE.environment_path()
        self.assertNotEqual(first, second)

    def test_validator_paths_are_scoped_to_codex_home(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.dict(VALIDATE.os.environ, {"CODEX_HOME": temp_dir}):
                skill_validator, plugin_validator = VALIDATE.validator_paths()
            root = Path(temp_dir) / "skills/.system"
            self.assertEqual(skill_validator, root / "skill-creator/scripts/quick_validate.py")
            self.assertEqual(plugin_validator, root / "plugin-creator/scripts/validate_plugin.py")


if __name__ == "__main__":
    unittest.main()
