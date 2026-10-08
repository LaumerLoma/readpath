# sim — the model behind the study

Every LLM here is a black box: a `BlackBoxModel(latency, quality)`. Nothing looks inside a model.
See the [top-level README](../README.md) for the question, assumptions A1–A8, and results.

This package runs the experiments in [3 · Experiments](../3-experiments/). The theorems in
[1 · Theory](../1-theory/) hold for every verifier and server and need no code; the experiments
check the bounds numerically and simulate what happens to a population of agents once they hold,
under illustrative parameters.

| Module | Contents |
|---|---|
| `readpath_sim/models.py` | Black-box models, the per-generation model catalog (A6), the verifier's judge (A4). |
| `readpath_sim/oracles.py` | Retrieval latency with a physical floor (A2) and the fabricator's padding strategy. |
| `readpath_sim/theory.py` | Closed forms for Propositions 1, 2, 4 and 5. |
| `readpath_sim/network.py` | The agent-to-agent network under a speed arms race (E5). |
| `readpath_sim/experiments.py` | E1–E5 and the E5 treatments: runs them, computes statistics over seeds, writes `results.json` and READMEs for the treatments. |
| `readpath_sim/figures.py` | Plots the figures in `../3-experiments/`. |
| `readpath_sim/measure.py` | Measures a real HTTP endpoint (latency, canary answer rate) to place it in the model. |

```bash
pip install -r requirements.txt
python3 -m readpath_sim               # E1–E5 into ../3-experiments/
python3 -m readpath_sim e5 --seeds 20 # one experiment, more seeds
python3 -m unittest discover -s tests
```

All parameters are illustrative. Change them in `NetworkParams`, `Catalog`, `Judge`, and
`RetrievalLatency`.
