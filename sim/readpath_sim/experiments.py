"""Experiments E1–E5. Each writes its figure and results.json into its folder in 3-experiments/.

E1 and E2 check the bounds of 1-theory/ numerically. E3 and E4 evaluate the closed forms of
2-game-theory/. E5 runs the network under every treatment, with several seeds each.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np

from . import figures, theory
from .models import Catalog, Judge
from .network import NetworkParams, run
from .oracles import RetrievalLatency

FOLDERS = {
    "e1": "01-timing",
    "e2": "02-checking",
    "e3": "03-corroboration",
    "e4": "04-anchors",
    "e5": "05-network",
}

BASE = NetworkParams()
TREATMENTS = {  # slug: (description, parameters)
    "baseline": ("current SOP", BASE),
    "stricter-judge": ("stricter judge (equal-quality fake passes 2%, not 12%)", replace(BASE, judge=Judge(bias=-4.0))),
    "reputation-penalty-4x": ("4× reputation penalty per rejected answer", replace(BASE, rejection_penalty=2.0)),
    "no-relay": ("no relaying between agents", replace(BASE, relay_probability=0.0)),
    "ask-8-servers": ("clients ask 8 agents, not 4", replace(BASE, servers_per_query=8)),
    "slower-arms-race": ("slower arms race (speed ×1.5 per generation)", replace(BASE, catalog=Catalog(speedup=1.5))),
    "timestamp-provenance": ("SOP + timestamp provenance", replace(BASE, require_provenance=True)),
    "control-no-speed-gains": ("control: no speed gains", replace(BASE, frozen_models=True)),
}

# Two-sided 97.5% quantiles of Student's t, by degrees of freedom.
_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
         9: 2.262, 10: 2.228, 15: 2.131, 20: 2.086, 30: 2.042}


def t975(df: int) -> float:
    """Conservative: between tabulated values, use the next smaller df (a larger quantile)."""
    if df > 30:
        return 1.96
    return _T975[max(k for k in _T975 if k <= df)]


def describe(samples: np.ndarray) -> dict:
    """Mean, sd, 95% CI half-width, min and max over axis 0 (the seeds)."""
    n = samples.shape[0]
    sd = samples.std(0, ddof=1) if n > 1 else np.zeros(samples.shape[1:])
    ci = t975(n - 1) * sd / np.sqrt(n) if n > 1 else sd
    return {k: np.round(v, 4).tolist() for k, v in
            dict(mean=samples.mean(0), sd=sd, ci95=ci, min=samples.min(0), max=samples.max(0)).items()}


def _write(folder: Path, data: dict):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "results.json").write_text(json.dumps(data, indent=1) + "\n")


# E1 -------------------------------------------------------------------------------------------

def e1_timing(out: Path, seeds: int):
    honest = RetrievalLatency()
    samples = 20_000
    latencies = np.logspace(-1.5, 1.3, 9)
    empirical = np.array([[theory.timing_advantage_empirical(l, honest, np.random.default_rng(s), samples)
                           for l in latencies] for s in range(seeds)])
    closed = np.array([theory.timing_advantage(l, honest) for l in latencies])
    critical = 1.358 * np.sqrt(2 / samples)  # two-sample KS, alpha = 0.05, n = m
    stats = describe(empirical)
    _write(out, {
        "experiment": "E1 timing",
        "claim": "best timing advantage equals F_R(l_G) and is 0 below the retrieval floor",
        "seeds": seeds, "samples_per_side": samples,
        "ks_critical_value_alpha_0.05": round(float(critical), 4),
        "latency_s": np.round(latencies, 4).tolist(),
        "closed_form": np.round(closed, 4).tolist(),
        "empirical_ks": stats,
        "max_abs_error_of_mean": round(float(np.abs(empirical.mean(0) - closed).max()), 4),
    })
    figures.fig_timing(out, honest, latencies, stats)
    return f"E1 max |KS - F_R(l_G)| = {np.abs(empirical.mean(0) - closed).max():.4f} (critical {critical:.4f})"


# E2 -------------------------------------------------------------------------------------------

def e2_checking(out: Path, seeds: int):
    honest, judge = RetrievalLatency(), Judge()
    samples = 300
    lat = np.logspace(-2.5, 1.3, 60)
    gap = np.linspace(-0.5, 0.5, 41)
    rng = np.random.default_rng(0)
    grid = np.array([[theory.fabricated_pass_rate(l, g, judge, honest, rng, samples) for l in lat] for g in gap])
    se = np.sqrt(grid * (1 - grid) / samples)
    p_equal = float(judge.single_pass(0.5, 0.5))
    retries = {f"{g:+.1f}": round(theory.retries_to_match(float(judge.single_pass(0.5 + g, 0.5)), judge.false_reject), 1)
               for g in (-0.2, -0.1, 0.0, 0.1, 0.2)}
    _write(out, {
        "experiment": "E2 checking",
        "claim": "best-of-n against the verifier's check reaches the honest pass rate once n >= ln(beta)/ln(1-p)",
        "samples_per_cell": samples, "max_standard_error": round(float(se.max()), 4),
        "false_reject_beta": judge.false_reject,
        "single_pass_equal_quality": round(p_equal, 4),
        "retries_to_match_by_quality_gap": retries,
        "latency_s": np.round(lat, 5).tolist(),
        "quality_gap": np.round(gap, 3).tolist(),
        "pass_rate": np.round(grid, 4).tolist(),
    })
    figures.fig_checking(out, lat, gap, grid, judge)
    return f"E2 equal quality: p = {p_equal:.3f}, retries to match = {retries['+0.0']}"


# E3 -------------------------------------------------------------------------------------------

def e3_corroboration(out: Path, seeds: int):
    ks = list(range(1, 9))
    coverages = {"common": 0.9, "uncommon": 0.5, "rare": 0.2}
    posterior = {name: [round(theory.posterior_honest(k, c), 4) for k in ks] for name, c in coverages.items()}
    _write(out, {
        "experiment": "E3 corroboration",
        "claim": "P(retrieved | k agree) = pi a^k / (pi a^k + 1 - pi) falls with k",
        "prior_honest": 0.9, "coverage": coverages, "k": ks, "posterior_retrieved": posterior,
        "note": "closed form; no sampling, so no confidence intervals",
    })
    figures.fig_corroboration(out, ks, coverages, posterior)
    return f"E3 rare question: posterior {posterior['rare'][0]:.2f} at k=1 -> {posterior['rare'][-1]:.4f} at k=8"


# E4 -------------------------------------------------------------------------------------------

def e4_anchors(out: Path, seeds: int):
    gens = list(range(15))
    exponents = [0.7, 0.9, 1.1]
    share = {str(s): [round(theory.anchored_coverage(g, s), 4) for g in gens] for s in exponents}
    _write(out, {
        "experiment": "E4 anchors",
        "claim": "the traffic share a fabricator can pre-commit grows as generation cost halves",
        "budget_answers_gen0": 1e4, "universe": 100_000_000, "generation": gens,
        "share_by_zipf_exponent": share,
        "note": "closed form; no sampling, so no confidence intervals",
    })
    figures.fig_anchors(out, gens, share)
    return f"E4 Zipf 0.9: pre-committed share {share['0.9'][0]:.2f} at gen 0 -> {share['0.9'][12]:.2f} at gen 12"


# E5 -------------------------------------------------------------------------------------------

def _job(args):
    slug, seed = args
    return slug, seed, run(TREATMENTS[slug][1], seed)


def _cross(adv_mean: list[float]) -> str:
    below = [i for i, a in enumerate(adv_mean) if a < 0.5]
    return str(below[0]) if below else "never"


def _treatment_readme(folder: Path, slug: str, description: str, changed: dict, seeds: int, stats: dict):
    rows = [("Verifier advantage", "advantage"), ("Fabricator share of agents", "fabricator_share"),
            ("Fabricated share of accepted answers", "fabricated_accepted_share"),
            ("True share of accepted answers", "precision"), ("Answer rate", "answer_rate"),
            ("Accepted fabrications laundered by an honest relay", "relay_laundered_share")]
    gens = [0, 4, 8, 12]
    params = "\n".join(f"- `{k} = {v}`" for k, v in changed.items()) or "- none: this is the baseline"
    table = "\n".join(f"| {label} | " + " | ".join(f"{stats[k]['mean'][g]:.2f} ± {stats[k]['ci95'][g]:.2f}" for g in gens) + " |"
                      for label, k in rows)
    (folder / "README.md").write_text(
        f"<!-- generated by `python3 -m readpath_sim e5`; do not edit -->\n\n"
        f"# E5 treatment · {description}\n\n"
        f"Parameters changed from the [baseline](../baseline/):\n\n{params}\n\n"
        f"Mean ± 95% CI (Student's t) over {seeds} seeds. Every generation and every seed: "
        f"[`results.json`](results.json).\n\n"
        f"| Generation | " + " | ".join(map(str, gens)) + " |\n|---|" + "---|" * len(gens) + f"\n{table}\n")


def e5_network(out: Path, seeds: int):
    jobs = [(slug, s) for slug in TREATMENTS for s in range(seeds)]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
        done = sorted(pool.map(_job, jobs), key=lambda d: (d[0], d[1]))
    raw = {slug: {k: np.stack([r[k] for s_, _, r in done if s_ == slug]) for k in done[0][2]} for slug in TREATMENTS}

    summary = {}
    for slug, (description, params) in TREATMENTS.items():
        stats = {k: describe(v) for k, v in raw[slug].items()}
        changed = {f: repr(getattr(params, f)) for f in params.__dataclass_fields__
                   if getattr(params, f) != getattr(BASE, f)}
        _write(out / "treatments" / slug, {
            "experiment": "E5 network", "treatment": slug, "description": description,
            "changed_parameters": changed, "seeds": seeds, "generations": params.generations,
            "by_generation": stats,
            "per_seed": {k: np.round(v, 4).tolist() for k, v in raw[slug].items()},
        })
        summary[slug] = stats
        _treatment_readme(out / "treatments" / slug, slug, description, changed, seeds, stats)

    rows = ["| Treatment | Advantage, gen 0 | Advantage, gen 12 | First gen. with mean advantage < 0.5 "
            "| Fabricated share of accepted, gen 12 | True share of accepted, gen 12 | Answer rate, gen 12 |",
            "|---|---|---|---|---|---|---|"]
    for slug, (description, _) in TREATMENTS.items():
        s = summary[slug]
        cell = lambda k, g: f"{s[k]['mean'][g]:.2f} ± {s[k]['ci95'][g]:.2f}"
        rows.append(f"| [{description}]({slug}/) | {cell('advantage', 0)} | "
                    f"{cell('advantage', -1)} | {_cross(s['advantage']['mean'])} | "
                    f"{cell('fabricated_accepted_share', -1)} | {cell('precision', -1)} | {cell('answer_rate', -1)} |")
    table = "\n".join(rows)
    (out / "treatments").mkdir(parents=True, exist_ok=True)
    (out / "treatments" / "summary.md").write_text(
        f"<!-- generated by `python3 -m readpath_sim e5`; do not edit -->\n\n"
        f"Mean ± 95% CI (Student's t) over {seeds} seeds per treatment.\n\n{table}\n")

    figures.fig_network(out, summary, raw)
    figures.fig_treatments(out, summary, {slug: d for slug, (d, _) in TREATMENTS.items()})
    return "E5 treatments:\n" + table


EXPERIMENTS = {"e1": e1_timing, "e2": e2_checking, "e3": e3_corroboration, "e4": e4_anchors, "e5": e5_network}
