import unittest

from experiments.routing_policy_replay import run


class RoutingPolicyReplayTests(unittest.TestCase):
    def test_ten_profile_replay_eliminates_known_unsafe_routes(self):
        result = run()
        self.assertEqual(result["profiles"], 10)
        self.assertEqual(
            result["summary"],
            {
                "changed_routes": 4,
                "unsafe_incomplete_luna_before": 3,
                "unsafe_incomplete_luna_after": 0,
                "sol_self_review_before": 1,
                "sol_self_review_after": 0,
                "sol_review_spawn_delta": 1,
            },
        )
