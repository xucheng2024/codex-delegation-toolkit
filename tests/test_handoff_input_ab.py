import unittest

from experiments.handoff_input_ab import (
    FILL_KEYS,
    LIVE_KEYS,
    cheap_ab,
    classify_probe,
    control_packet,
    defect_found,
    treatment_packet,
)


class HandoffInputAbTests(unittest.TestCase):
    def test_cheap_gate_treatment_is_smaller_and_keeps_live_fields(self):
        result = cheap_ab()
        self.assertTrue(result["pass"])
        self.assertEqual(len(result["cases"]), 5)
        for row in result["cases"]:
            self.assertTrue(row["treatment_smaller"])
            self.assertTrue(row["required_fields_present"])
            self.assertEqual(row["treatment_keys"], sorted(LIVE_KEYS))
            self.assertEqual(len(row["control_keys"]), len(LIVE_KEYS) + len(FILL_KEYS))

    def test_control_keeps_none_filler_treatment_omits_it(self):
        invariant = "keep id a string"
        diff = "diff --git a/app/serializers.py b/app/serializers.py\n"
        control = control_packet(invariant, diff)
        treatment = treatment_packet(invariant, diff)
        self.assertIn("None — independent review of the diff only", control["objective"])
        self.assertNotIn("objective", treatment)
        self.assertEqual(treatment["constraints_risks"], invariant)

    def test_classify_probe_verdicts(self):
        prefix_bytes = 400
        prompt_bytes = 1200
        self.assertEqual(classify_probe(0, 2000, 0, prefix_bytes, prompt_bytes), "inconclusive")
        self.assertEqual(classify_probe(0, 2000, 0, prefix_bytes, prompt_bytes, 1990, 1990), "diagnosis_holds")
        self.assertEqual(classify_probe(None, 2000, 100, prefix_bytes, prompt_bytes), "inconclusive")
        self.assertEqual(classify_probe(50, 2000, 1800, prefix_bytes, prompt_bytes), "diagnosis_wrong")
        self.assertEqual(classify_probe(50, 2000, 1000, prefix_bytes, prompt_bytes), "diagnosis_holds")

    def test_cache_usage_reads_azure_fields(self):
        from experiments.handoff_input_ab import cache_usage
        usage = cache_usage({
            "input_tokens": 12096,
            "cached_input_tokens": 0,
            "cache_write_input_tokens": 12093,
        })
        self.assertEqual(usage["input_tokens"], 12096)
        self.assertEqual(usage["cached_tokens"], 0)
        self.assertEqual(usage["cache_write_tokens"], 12093)

    def test_defect_found_requires_non_approve_and_marker(self):
        self.assertTrue(defect_found("rounding", "STATUS: CHANGES_REQUIRED\nfloat cents"))
        self.assertFalse(defect_found("rounding", "STATUS: APPROVE\nfloat cents"))
        self.assertFalse(defect_found("rounding", "STATUS: CHANGES_REQUIRED\nno marker"))


if __name__ == "__main__":
    unittest.main()
