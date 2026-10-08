"""Figures for 3-experiments/. Minimal style: serif text, one accent colour, greys for the rest."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from . import theory  # noqa: E402

ACCENT = "#b3261e"
INK = "#1a1a1a"
GREY = "#8a8a8a"
LIGHT = "#c8c8c8"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Georgia", "Source Serif Pro", "DejaVu Serif"],
    "font.size": 10,
    "axes.edgecolor": INK,
    "axes.labelcolor": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titlesize": 10.5,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "xtick.color": INK,
    "ytick.color": INK,
    "legend.frameon": False,
    "svg.fonttype": "none",
    "figure.dpi": 120,
})


def _save(fig, out: Path, name: str):
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.svg", bbox_inches="tight")
    fig.savefig(out / f"{name}.png", bbox_inches="tight", dpi=160)
    plt.close(fig)


def fig_timing(out: Path, honest, latencies, stats):
    xs = np.logspace(-2, 1.5, 200)
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.plot(xs, [theory.timing_advantage(x, honest) for x in xs], color=ACCENT, lw=2,
            label="best timing test, closed form $F_R(\\ell_G)$")
    ax.errorbar(latencies, stats["mean"], yerr=stats["ci95"], fmt="o", color=INK, ms=4, capsize=2,
                label="simulated KS distance (mean, 95% CI)")
    ax.axvspan(xs[0], honest.floor, color=LIGHT, alpha=0.5, lw=0)
    ax.text(0.012, 0.55, "generation faster than\nthe retrieval floor:\nadvantage = 0", color=INK, fontsize=9)
    ax.set_xscale("log")
    ax.set_xlabel("fabricator model latency per answer $\\ell_G$ (s)")
    ax.set_ylabel("verifier advantage")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("E1 · Timing stops working once generation beats retrieval")
    ax.legend(loc="center right", fontsize=8.5)
    _save(fig, out, "timing")


def fig_checking(out: Path, lat, gap, grid, judge):
    fig, ax = plt.subplots(figsize=(6, 3.4))
    mesh = ax.pcolormesh(lat, gap, grid, cmap="Greys", vmin=0, vmax=1, shading="auto")
    ax.contour(lat, gap, grid, levels=[1 - judge.false_reject], colors=[ACCENT], linewidths=2)
    ax.text(0.03, 0.06, "right of the red line: fabricated answers\npass as often as honest ones",
            color=ACCENT, fontsize=8.5, ha="left", va="bottom", transform=ax.transAxes)
    ax.set_xscale("log")
    ax.invert_xaxis()
    ax.set_xlabel("fabricator model latency per answer (s); faster to the right")
    ax.set_ylabel("fabricator quality − verifier quality")
    ax.set_title("E2 · Speed buys retries against the verifier's own check")
    fig.colorbar(mesh, ax=ax, label="P(fabricated answer accepted)")
    _save(fig, out, "checking")


def fig_corroboration(out: Path, ks, coverages, posterior):
    fig, ax = plt.subplots(figsize=(6, 3.2))
    for (name, cov), colour in zip(coverages.items(), [LIGHT, GREY, ACCENT]):
        ax.plot(ks, posterior[name], "o-", color=colour, lw=2, ms=4, label=f"{name} question (coverage {cov})")
    ax.set_xlabel("number of sources that agree")
    ax.set_ylabel("P(retrieved | all agree)\nprior 0.9")
    ax.set_ylim(0, 1.02)
    ax.set_title("E3 · On rare questions, agreement is evidence of fabrication")
    ax.legend(fontsize=8.5)
    _save(fig, out, "corroboration")


def fig_anchors(out: Path, gens, share):
    fig, ax = plt.subplots(figsize=(6, 3.2))
    for (s, values), colour in zip(share.items(), [ACCENT, GREY, LIGHT]):
        ax.plot(gens, values, "o-", color=colour, lw=2, ms=3.5, label=f"Zipf exponent {s}")
    ax.set_xlabel("model generation (generation cost halves each step)")
    ax.set_ylabel("traffic share pre-committed")
    ax.set_ylim(0, 1.02)
    ax.set_title("E4 · Anchors force pre-commitment, which gets cheaper")
    ax.legend(fontsize=8.5)
    _save(fig, out, "anchors")


SCENARIOS = [
    ("baseline", "current SOP", ACCENT, "-"),
    ("timestamp-provenance", "SOP + timestamp provenance", INK, "-"),
    ("control-no-speed-gains", "control: no speed gains", GREY, "--"),
]


def fig_network(out: Path, summary, raw):
    panels = [
        ("advantage", "verifier advantage\n(retrieved vs fabricated)", (-0.1, 1.0)),
        ("fabricated_accepted_share", "share of accepted answers\nthat were fabricated", (0, 1.0)),
        ("precision", "share of accepted answers\nthat are true", (0, 1.0)),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharex=True)
    gens = np.arange(raw["baseline"]["advantage"].shape[1])
    for ax, (key, label, ylim) in zip(axes, panels):
        for name, legend, colour, style in SCENARIOS:
            data = raw[name][key]
            ax.fill_between(gens, data.min(0), data.max(0), color=colour, alpha=0.15, lw=0)
            ax.plot(gens, data.mean(0), style, color=colour, lw=2, label=legend)
        ax.set_ylim(*ylim)
        ax.set_ylabel(label)
        ax.set_xlabel("model generation (speed ×2 each)")
        ax.set_xticks(gens[::2])
    lat = summary["baseline"]["median_model_latency"]["mean"]
    top = axes[0].secondary_xaxis("top")
    ticks = gens[::3]
    top.set_xticks(ticks)
    top.set_xticklabels([f"{lat[t]:.2g}s" for t in ticks], fontsize=8)
    top.set_xlabel("median agent model latency", fontsize=8.5)
    axes[0].axhline(0, color=LIGHT, lw=0.8)
    axes[2].legend(loc="lower left", fontsize=8.5)
    fig.suptitle("E5 · Agent-to-agent traffic: speed gains alone collapse trust",
                 x=0.01, ha="left", fontweight="bold", fontsize=11)
    fig.tight_layout()
    _save(fig, out, "network")


def fig_treatments(out: Path, summary, descriptions):
    import textwrap

    others = [slug for slug in summary if slug != "baseline"]
    fig, axes = plt.subplots(2, 4, figsize=(12, 5.6), sharex=True, sharey=True)
    base = summary["baseline"]
    gens = np.arange(len(base["advantage"]["mean"]))

    def band(ax, stats, key, colour, style, label=None):
        mean, ci = np.array(stats[key]["mean"]), np.array(stats[key]["ci95"])
        ax.fill_between(gens, mean - ci, mean + ci, color=colour, alpha=0.15, lw=0)
        ax.plot(gens, mean, style, color=colour, lw=1.8, label=label)

    for ax, slug in zip(axes.flat, others):
        band(ax, base, "advantage", ACCENT, "-", "current SOP: advantage")
        band(ax, base, "precision", ACCENT, ":", "current SOP: true share")
        band(ax, summary[slug], "advantage", INK, "-", "treatment: advantage")
        band(ax, summary[slug], "precision", INK, ":", "treatment: true share")
        ax.set_title(textwrap.fill(descriptions[slug], 34), fontsize=9)
        ax.set_ylim(-0.1, 1.02)
        ax.set_xticks(gens[::4])
    axes.flat[-1].axis("off")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    axes.flat[-1].legend(handles, labels, loc="center", fontsize=8.5)
    for ax in axes[1]:
        ax.set_xlabel("model generation")
    for ax in axes[:, 0]:
        ax.set_ylabel("share or advantage")
    fig.suptitle("E5 · Each treatment against the current SOP (mean, 95% CI over seeds)",
                 x=0.01, ha="left", fontweight="bold", fontsize=11)
    fig.tight_layout()
    _save(fig, out, "treatments")
