"""Closed forms for Propositions 1 and 2 (1-theory/) and 4 and 5 (2-game-theory/). Every parameter is illustrative, not measured."""

from __future__ import annotations

import numpy as np

from .models import BlackBoxModel, Judge
from .oracles import RetrievalLatency, fabricator_response


# Proposition 1 -------------------------------------------------------------------------------------

def timing_advantage(gen_latency: float, honest: RetrievalLatency) -> float:
    """Best advantage of any test that sees only response times.

    The padded fabricator answers at ``max(d, l_G)`` with ``d ~ L_R``. That distribution equals
    ``L_R`` except that the mass below ``l_G`` moves to an atom at ``l_G``, so the total variation
    distance -- the best possible advantage -- is ``F_R(l_G)``. It is exactly 0 once
    ``l_G <= floor``.
    """

    return honest.cdf(gen_latency)


def timing_advantage_empirical(gen_latency, honest, rng, samples=20_000):
    """Kolmogorov-Smirnov distance between simulated fabricator and honest response times.

    KS is a lower bound on total variation; for the padded fabricator both equal F_R(l_G).
    """

    model = BlackBoxModel(gen_latency, 0.5)
    fab = np.sort([fabricator_response(model, honest, rng)[0] for _ in range(samples)])
    ret = np.sort(honest.sample(rng, samples))
    grid = np.concatenate([fab, ret])
    f_fab = np.searchsorted(fab, grid, side="right") / samples
    f_ret = np.searchsorted(ret, grid, side="right") / samples
    return float(np.abs(f_fab - f_ret).max())


# Proposition 2 -------------------------------------------------------------------------------------

def fabricated_pass_rate(gen_latency, quality_gap, judge: Judge, honest: RetrievalLatency, rng, samples=400):
    """Chance that a padded, best-of-n fabricated answer passes the verifier's check.

    ``quality_gap`` = fabricator quality minus verifier quality.
    """

    d = honest.sample(rng, samples)
    n = np.maximum(1, np.floor(d / gen_latency))
    return float(judge.best_of_n_pass(0.5 + quality_gap, 0.5, n).mean())


def retries_to_match(p_single: float, false_reject: float) -> float:
    """Retries after which the fabricator passes as often as an honest answer:
    ``1-(1-p)^n >= 1-beta`` iff ``n >= ln(beta)/ln(1-p)``."""

    return float(np.log(false_reject) / np.log1p(-p_single))


# Proposition 4 -------------------------------------------------------------------------------------

def posterior_honest(k: int, coverage: float, prior_honest: float = 0.9) -> float:
    """P(honest world | k of k sources agree).

    Honest world: each independent source has the answer with probability ``coverage``.
    Fabricated world: one operator serves all k sources and always answers (cost k*c_gen,
    assumed affordable). The likelihood ratio is ``coverage**k``, so on rare questions
    (small coverage) each extra agreeing source is evidence *for* fabrication.
    """

    h = prior_honest * coverage**k
    return float(h / (h + (1.0 - prior_honest)))


# Proposition 5 -------------------------------------------------------------------------------------

def _harmonic(n: int, s: float, exact_up_to: int = 1_000_000) -> float:
    """Generalized harmonic number sum_{i<=n} i^-s, exact head plus an integral tail."""

    head = min(n, exact_up_to)
    total = float((np.arange(1, head + 1, dtype=float) ** (-s)).sum())
    if n > head:
        a, b = head + 0.5, n + 0.5
        total += np.log(b / a) if s == 1 else (b ** (1 - s) - a ** (1 - s)) / (1 - s)
    return total


def anchored_coverage(gen: int, zipf_s: float, universe: int = 100_000_000, budget: float = 1e4,
                      cost0: float = 1.0, speedup: float = 2.0) -> float:
    """Share of query traffic a fabricator can pre-commit before the queries arrive.

    Anchors (a signature, an archive snapshot, a timestamp that predates the query) defeat
    on-demand fabrication. The fabricator must instead commit answers in advance. With budget
    ``B`` and cost ``c(t) = c0 / speedup**t`` per answer, it commits the ``B/c(t)`` most popular
    queries of a Zipf(s) distribution over ``universe`` distinct questions.
    """

    covered = int(min(universe, budget * speedup**gen / cost0))
    return _harmonic(covered, zipf_s) / _harmonic(universe, zipf_s)
