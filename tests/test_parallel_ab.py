import importlib.util
import unittest
from pathlib import Path
ROOT = Path(__file__).parents[1]; SCRIPT = ROOT / "experiments/parallel_ab.py"
SPEC = importlib.util.spec_from_file_location("parallel_ab", SCRIPT); AB = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(AB)
class ParallelABTests(unittest.TestCase):
    def test_summary_compares_time_and_priced_cost(self):
        result = AB.summarize([{"arm":"serial","success":True,"elapsed_ms":1200,"cost_usd":0.03,"usage_rows":2},{"arm":"parallel","success":True,"elapsed_ms":700,"cost_usd":0.04,"usage_rows":3}])
        self.assertEqual(result["directional"]["time_saved_ms"], 500); self.assertAlmostEqual(result["directional"]["cost_delta_usd"], 0.01)
    def test_summary_never_invents_missing_cost(self):
        result = AB.summarize([{"arm":"serial","success":True,"elapsed_ms":1200,"cost_usd":None,"usage_rows":0},{"arm":"parallel","success":True,"elapsed_ms":700,"cost_usd":0.04,"usage_rows":1}])
        self.assertIsNone(result["directional"]["cost_delta_usd"])
if __name__ == "__main__": unittest.main()
