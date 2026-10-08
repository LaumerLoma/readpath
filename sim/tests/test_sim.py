import unittest

import numpy as np

from readpath_sim import theory
from readpath_sim.models import Judge
from readpath_sim.network import NetworkParams, run
from readpath_sim.oracles import RetrievalLatency


class Theory(unittest.TestCase):
    def test_timing_advantage_is_zero_below_floor(self):
        honest = RetrievalLatency()
        self.assertEqual(theory.timing_advantage(honest.floor * 0.5, honest), 0.0)
        self.assertGreater(theory.timing_advantage(20.0, honest), 0.99)

    def test_simulated_timing_matches_closed_form(self):
        honest, rng = RetrievalLatency(), np.random.default_rng(1)
        for latency in (0.1, 1.5, 4.0):
            self.assertAlmostEqual(theory.timing_advantage_empirical(latency, honest, rng),
                                   theory.timing_advantage(latency, honest), delta=0.03)

    def test_retries_reach_honest_pass_rate(self):
        judge = Judge()
        p = float(judge.single_pass(0.5, 0.5))
        n = int(np.ceil(theory.retries_to_match(p, judge.false_reject)))
        self.assertGreaterEqual(float(judge.best_of_n_pass(0.5, 0.5, n)), 1 - judge.false_reject)

    def test_agreement_lowers_posterior_on_rare_questions(self):
        values = [theory.posterior_honest(k, 0.2) for k in range(1, 6)]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_anchor_coverage_grows_with_cheaper_generation(self):
        values = [theory.anchored_coverage(g, 0.9) for g in range(0, 15, 2)]
        self.assertEqual(values, sorted(values))
        self.assertAlmostEqual(values[-1], 1.0, places=6)


class Network(unittest.TestCase):
    small = dict(agents=80, rounds_per_generation=4, generations=11)

    def test_speed_gains_collapse_advantage(self):
        out = run(NetworkParams(**self.small), seed=0)
        self.assertLess(out["advantage"][-1], 0.3)
        self.assertGreater(out["fabricated_accepted_share"][-1], 0.4)

    def test_control_keeps_advantage(self):
        out = run(NetworkParams(frozen_models=True, **self.small), seed=0)
        self.assertGreater(out["advantage"][-1], 0.6)
        self.assertLess(out["fabricated_accepted_share"][-1], 0.1)


if __name__ == "__main__":
    unittest.main()
