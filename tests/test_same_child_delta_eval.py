import unittest

from experiments.same_child_delta_eval import cheap_ab, delta_prompt


class SameChildDeltaEvalTests(unittest.TestCase):
    def test_cheap_delta_is_smaller_than_rebuilt_capsule(self):
        result = cheap_ab()
        self.assertTrue(result["pass"])
        self.assertLess(result["delta_bytes"], result["rebuilt_bytes"])
        self.assertLess(result["byte_ratio"], 0.5)

    def test_delta_is_instruction_not_capsule(self):
        text = delta_prompt("keep id a string", "diff --git a/app/x.py b/app/x.py\n")
        self.assertIn("Do not rebuild a handoff capsule", text)
        self.assertNotIn("CACHE_HANDOFF_V1", text)
        self.assertNotIn("DYNAMIC_PACKET_JSON", text)


if __name__ == "__main__":
    unittest.main()
