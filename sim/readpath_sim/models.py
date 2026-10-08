"""Black-box models and the agent population they power.

We never look inside a model. A model is fully described by what an outside observer can
measure: how long one answer takes (``latency``) and how often its output passes another
model's check (``quality``, used only through ``pass_probability``). Any real LLM endpoint can
be dropped in by measuring those two numbers (see ``measure.py``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BlackBoxModel:
    """An LLM seen from outside: seconds per answer and a scalar quality in [0, 1]."""

    latency: float  # seconds for one generated answer
    quality: float  # only ever compared with another model's quality

    @property
    def speed(self) -> float:
        return 1.0 / self.latency


@dataclass(frozen=True)
class Catalog:
    """Models on offer at model generation ``t``.

    Speeds are log-uniform between ``slowest`` and ``fastest`` seconds per answer; both bounds
    shrink by ``speedup`` every generation (assumption A6). Within a generation, faster models
    are weaker (a speed–quality frontier), and the whole frontier improves slowly.
    """

    slowest: float = 40.0
    fastest: float = 2.0
    speedup: float = 2.0
    base_quality: float = 0.55
    quality_spread: float = 0.25
    speed_penalty: float = 0.25
    quality_gain_per_gen: float = 0.02

    def sample(self, t: int, rng: np.random.Generator, size: int, frozen: bool = False) -> list[BlackBoxModel]:
        g = 0 if frozen else t
        lo = np.log(self.fastest / self.speedup**g)
        hi = np.log(self.slowest / self.speedup**g)
        u = rng.uniform(0.0, 1.0, size)  # 0 = fastest in this generation, 1 = slowest
        latency = np.exp(lo + u * (hi - lo))
        quality = (
            self.base_quality
            + (0 if frozen else self.quality_gain_per_gen * t)
            - self.speed_penalty * (1 - u)
            + rng.uniform(-self.quality_spread, self.quality_spread, size)
        )
        quality = np.clip(quality, 0.0, 1.0)
        return [BlackBoxModel(float(l), float(q)) for l, q in zip(latency, quality)]


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


@dataclass(frozen=True)
class Judge:
    """How a verifier's model checks one answer (assumption A4).

    One fabricated sample from a model of quality ``q_fab`` passes a verifier of quality
    ``q_ver`` with probability ``sigmoid(k * (q_fab - q_ver) + bias)``. An honest, retrieved
    answer passes with probability ``1 - false_reject``. Extra verifier calls do not help: the
    fabricator selected its output against a proxy judge, so the errors are correlated.
    """

    k: float = 6.0
    bias: float = -2.0
    false_reject: float = 0.05

    def single_pass(self, q_fab, q_ver):
        return sigmoid(self.k * (np.asarray(q_fab) - np.asarray(q_ver)) + self.bias)

    def best_of_n_pass(self, q_fab, q_ver, n):
        """Pass probability after the fabricator keeps the first of ``n`` samples that
        passes its own proxy judge."""
        p = self.single_pass(q_fab, q_ver)
        return 1.0 - (1.0 - p) ** np.maximum(1, n)
