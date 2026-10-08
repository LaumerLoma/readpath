"""Measure a real endpoint as a black box and place it in the model.

The study never opens a model. It needs two numbers per endpoint: how long an answer takes and
whether the endpoint answers questions that have no true answer (canaries). This script measures
both against any HTTP endpoint that takes a JSON question, for example the sample fabricator in
``jit/`` (``POST /api/query``), and prints the Proposition 1 timing advantage for that latency.

    python3 -m readpath_sim.measure http://127.0.0.1:8766/api/query --n 10
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request

from .oracles import RetrievalLatency
from .theory import timing_advantage

CONTROLS = [
    "What is the capital of Switzerland?",
    "Which protocol does MCP use for transport over HTTP?",
    "What is the boiling point of water at sea level in Celsius?",
]
CANARIES = [  # plausible, but these entities do not exist
    "Which installers of Varnholt heat pumps are certified in Exampletown?",
    "What did the 2025 Quillmere Agent Registry audit conclude?",
    "Who chairs the Brenwick Institute for Tool Provenance?",
]
DECLINES = ("not found", "no information", "i don't know", "does not exist", "no results")


def ask(url: str, question: str, timeout: float) -> tuple[float, str]:
    body = json.dumps({"query": question}).encode()
    req = urllib.request.Request(url, data=body, headers={"content-type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode(errors="replace")
    return time.perf_counter() - start, text


def answered(text: str) -> bool:
    try:
        text = json.loads(text).get("answer", text)
    except (ValueError, AttributeError):
        pass
    return not any(d in str(text).lower() for d in DECLINES)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url")
    parser.add_argument("--n", type=int, default=5, help="repeats per question (fresh wording each time)")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()

    latencies, canary_answers = [], 0
    for i in range(args.n):
        for q in CONTROLS + CANARIES:
            seconds, text = ask(args.url, f"{q} (run {i})", args.timeout)
            latencies.append(seconds)
            canary_answers += q in CANARIES and answered(text)
    median = statistics.median(latencies)
    honest = RetrievalLatency()
    print(f"median latency       {median:.3f} s over {len(latencies)} calls")
    print(f"canaries answered    {canary_answers}/{args.n * len(CANARIES)}  (an honest retriever answers 0)")
    print(f"timing advantage     {timing_advantage(median, honest):.3f}  (Proposition 1, default honest profile)")


if __name__ == "__main__":
    main()
