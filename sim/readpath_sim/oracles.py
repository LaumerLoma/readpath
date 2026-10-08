"""The two oracles a verifier can face: retrieval (Ret) and on-demand generation (Fab_G)."""

from __future__ import annotations

from dataclasses import dataclass
from math import erf, log, sqrt

import numpy as np

from .models import BlackBoxModel


@dataclass(frozen=True)
class RetrievalLatency:
    """Honest response time: a physical floor plus log-normal I/O time (assumption A2).

    Retrieval has to touch the world (a database, a page, a disk), so it cannot get faster
    than ``floor`` however fast the model in front of it is. Generation has no such floor.
    """

    floor: float = 0.3
    median_io: float = 1.2
    sigma: float = 0.6

    def sample(self, rng: np.random.Generator, size=None):
        return self.floor + rng.lognormal(log(self.median_io), self.sigma, size)

    def cdf(self, x: float) -> float:
        if x <= self.floor:
            return 0.0
        z = (log(x - self.floor) - log(self.median_io)) / self.sigma
        return 0.5 * (1.0 + erf(z / sqrt(2.0)))

    def quantile(self, p: float) -> float:
        from statistics import NormalDist

        return self.floor + self.median_io * float(np.exp(self.sigma * NormalDist().inv_cdf(p)))


def fabricator_response(model: BlackBoxModel, honest: RetrievalLatency, rng: np.random.Generator):
    """Fab_G's padding strategy.

    Draw a target time ``d`` from the honest latency profile. Spend it on retries: ``n`` samples
    of ``model`` fit in ``d``. Answer at ``max(d, model.latency)``. If the model is faster than the
    honest floor, the observable latency is exactly the honest distribution (Proposition 1), and the
    spare time becomes ``n - 1`` retries against a proxy judge (Proposition 2).
    """

    d = float(honest.sample(rng))
    n = max(1, int(d // model.latency))
    return max(d, model.latency), n
