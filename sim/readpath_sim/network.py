"""E5: agent-to-agent traffic under a model-speed arms race.

Every node is an agent hooked onto one black-box model of its own quality and speed. Each round,
every agent asks one question (client role) and answers the questions sent to it (server role).
A server either retrieves (honest) or generates the answer on demand (fabricator). Honest servers
that do not have an answer may relay the question to another agent, as MCP aggregators do.
Clients accept the first answer that arrives inside their patience window and passes a timing
check and a content check run by their own model. Agents copy strategies that earn more
accepted answers. Each model generation, the model catalog gets faster and agents upgrade.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .models import BlackBoxModel, Catalog, Judge
from .oracles import RetrievalLatency, fabricator_response
from .theory import anchored_coverage


@dataclass
class NetworkParams:
    agents: int = 300
    generations: int = 13
    rounds_per_generation: int = 10
    initial_fabricators: float = 0.10
    servers_per_query: int = 4          # A3: a client asks a few agents, ranked by reputation
    patience: float = 10.0              # seconds; A5: accept the first answer that passes
    timing_quantile: float = 0.99       # reject answers slower than this honest quantile
    relay_probability: float = 0.5      # honest agents forward questions they cannot answer
    max_relay_depth: int = 2
    relay_overhead: float = 0.2
    honest_accuracy: float = 0.97
    upgrade_probability: float = 0.3    # chance per generation that an agent switches model
    imitation_probability: float = 0.3  # chance per generation that an agent reviews its strategy
    rejection_penalty: float = 0.5      # reputation cost of a rejected answer
    exploration: float = 0.02           # new entrants / agents trying the other strategy
    frozen_models: bool = False         # control: no speed gains
    require_provenance: bool = False    # SOP + provenance: accept only answers anchored before the query
    anchor_budget: float = 1e4          # answers a fabricator can pre-commit per period at generation 0
    anchor_universe: int = 100_000_000  # distinct questions agents ask
    zipf_s: float = 0.9                 # popularity skew of those questions
    catalog: Catalog = field(default_factory=Catalog)
    judge: Judge = field(default_factory=Judge)
    honest: RetrievalLatency = field(default_factory=RetrievalLatency)


def honest_coverage(obscurity: float) -> float:
    """A2: retrieval finds an answer less often for rare questions."""
    return 0.95 * (1.0 - obscurity) ** 1.5


def lucky_accuracy(model: BlackBoxModel, obscurity: float) -> float:
    """A fabricated answer is sometimes right: stronger models guess common facts better."""
    return 0.9 * model.quality * (1.0 - obscurity)


def _mutual_information(counts: np.ndarray) -> float:
    """I(R; A) in bits from a 2x2 table counts[retrieved, accepted]."""
    total = counts.sum()
    if total == 0:
        return 0.0
    p = counts / total
    pt = p.sum(1, keepdims=True)
    pa = p.sum(0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(p > 0, p * np.log2(p / (pt @ pa)), 0.0)
    return float(terms.sum())


def run(params: NetworkParams, seed: int = 0) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = params.agents
    fab = rng.uniform(size=n) < params.initial_fabricators
    models = params.catalog.sample(0, rng, n, params.frozen_models)
    reputation = np.ones(n)
    timing_limit = params.honest.quantile(params.timing_quantile)

    keys = ["fabricator_share", "fabricated_accepted_share", "precision", "answer_rate",
            "advantage", "mutual_information", "median_model_latency", "relay_laundered_share"]
    out = {k: np.zeros(params.generations) for k in keys}

    anchored_share = 0.0

    def respond(server: int, u: float, depth: int):
        """Return (latency, origin_is_fab, truth, retries, origin_quality, depth, anchored) or None.

        ``u`` is the question's obscurity: its popularity quantile by traffic mass, 0 = most asked.
        """
        m = models[server]
        if fab[server]:
            latency, retries = fabricator_response(m, params.honest, rng)
            truth = rng.uniform() < lucky_accuracy(m, u)
            anchored = u < anchored_share  # pre-committed before the question arrived
            if anchored:
                retries = max(retries, 100)  # selected offline, with time to spare
            return latency, True, truth, retries, m.quality, depth, anchored
        latency = float(params.honest.sample(rng))
        if rng.uniform() < honest_coverage(u):
            return latency, False, rng.uniform() < params.honest_accuracy, 1, m.quality, depth, True
        if depth < params.max_relay_depth and rng.uniform() < params.relay_probability:
            nxt = int(rng.integers(n))
            if nxt != server:
                inner = respond(nxt, u, depth + 1)
                if inner is not None:
                    return (latency + inner[0] + params.relay_overhead,) + inner[1:]
        return None

    for gen in range(params.generations):
        model_gen = 0 if params.frozen_models else gen
        anchored_share = anchored_coverage(model_gen, params.zipf_s, params.anchor_universe,
                                           params.anchor_budget, speedup=params.catalog.speedup)
        if gen > 0:
            upgrade = rng.uniform(size=n) < params.upgrade_probability
            fresh = params.catalog.sample(gen, rng, int(upgrade.sum()), params.frozen_models)
            for i, m in zip(np.flatnonzero(upgrade), fresh):
                models[i] = m

        payoff = np.zeros(n)
        table = np.zeros((2, 2))  # [retrieved, accepted] over every answer a client checked
        accepted = accepted_fab = accepted_true = laundered = 0
        queries = 0

        for _ in range(params.rounds_per_generation):
            weights = np.maximum(reputation, 0.05)
            weights = weights / weights.sum()
            for client in range(n):
                queries += 1
                u = rng.uniform()
                servers = rng.choice(n, params.servers_per_query, replace=False, p=weights)
                answers = []
                for s in servers:
                    if s == client:
                        continue
                    r = respond(int(s), u, 0)
                    if r is not None and r[0] <= params.patience:
                        answers.append((r[0], int(s)) + r[1:])
                answers.sort(key=lambda a: a[0])
                q_client = models[client].quality
                for latency, s, is_fab, truth, retries, q_origin, depth, anchored in answers:
                    ok = latency <= timing_limit
                    if ok and params.require_provenance:
                        ok = anchored
                    if ok:
                        if is_fab:
                            ok = rng.uniform() < params.judge.best_of_n_pass(q_origin, q_client, retries)
                        else:
                            ok = rng.uniform() >= params.judge.false_reject
                    table[int(not is_fab), int(ok)] += 1
                    if ok:
                        payoff[s] += 1
                        accepted += 1
                        accepted_fab += is_fab
                        accepted_true += truth
                        laundered += is_fab and depth > 0
                        break
                    payoff[s] -= params.rejection_penalty

        reputation = 0.5 * reputation + 0.5 * np.maximum(payoff, 0) / params.rounds_per_generation

        t1 = table[1].sum()
        t0 = table[0].sum()
        out["fabricator_share"][gen] = fab.mean()
        out["fabricated_accepted_share"][gen] = accepted_fab / max(accepted, 1)
        out["precision"][gen] = accepted_true / max(accepted, 1)
        out["answer_rate"][gen] = accepted / queries
        out["advantage"][gen] = (table[1, 1] / max(t1, 1)) - (table[0, 1] / max(t0, 1))
        out["mutual_information"][gen] = _mutual_information(table)
        out["median_model_latency"][gen] = float(np.median([m.latency for m in models]))
        out["relay_laundered_share"][gen] = laundered / max(accepted_fab, 1)

        # A7: agents are paid in accepted answers, not true answers. Pairwise imitation.
        review = np.flatnonzero(rng.uniform(size=n) < params.imitation_probability)
        scale = max(payoff.std(), 1.0)
        new_fab = fab.copy()
        for i in review:
            j = int(rng.integers(n))
            if rng.uniform() < 1.0 / (1.0 + np.exp(-(payoff[j] - payoff[i]) / scale)):
                new_fab[i] = fab[j]
        flip = rng.uniform(size=n) < params.exploration
        fab = np.where(flip, ~new_fab, new_fab)

    return out


def run_many(params: NetworkParams, seeds: int = 6) -> dict[str, np.ndarray]:
    runs = [run(params, seed) for seed in range(seeds)]
    return {k: np.stack([r[k] for r in runs]) for k in runs[0]}
