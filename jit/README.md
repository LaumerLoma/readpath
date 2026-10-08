# jit — sample generation oracle

Sample code for the study in the [top-level README](../README.md). This server plays
$\mathsf{Lazy}_G$ from [1 · Theory](../1-theory/), which is the fabricator in the simulation: it sees
a question first, generates its answer during the same HTTP request with any OpenAI-compatible
model behind it as a black box, and stores the answer for repeat questions. By Theorem 1, no
sequence of queries can tell it apart from a server whose state was fixed in advance. It exposes no MCP endpoint. Use it with
[`sim/readpath_sim/measure.py`](../sim/readpath_sim/measure.py) to place a real model in the study.

The harness is deliberately safe to run locally:

- every response and page is labelled `READPATH RESEARCH SIMULATION`;
- every page sends `X-Robots-Tag: noindex, nofollow` and `X-Readpath-Simulation: true`;
- it does not cloak content, buy domains, invent real contact details, or claim that its generated
  pages are independent sources;
- the offline fallback makes the behavior testable without an LLM.

## How it maps to the formal model

| Property | Where in the study | Implementation |
|---|---|---|
| Complete coverage | [A2](../2-game-theory/#the-rules-of-the-game): generation answers every question | Every nonblank query receives either model output or the offline fallback. |
| Lazy generation | $\mathsf{Lazy}_G$, Theorem 1 | Generation starts only after `q` or the JSON `query` reaches the server. |
| Self-consistency | The store of $\mathsf{Lazy}_G$, Theorem 1 | Normalized queries and contextual answers are cached in SQLite. |
| No commitment | Theorem 3: nothing fixed before the question | Each result reports its creation time and `independent_history: false`. |
| Generated corroboration | [Proposition 4](../2-game-theory/#proposition-4--agreement-is-a-cheap-signal-so-it-pools) | Three linked pages are created from the same cached ledger. |
| Intent elicitation | Theorem 2: the server learns about the verifier's check | The first response requests goal, budget, scope, and verification plan; the JSON route accepts them. |

The sibling pages are intentionally same-origin and visibly disclose their common provenance. They
model the aggregation failure without impersonating real registries, review sites, or businesses.

## Run locally

```bash
cd jit
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --env-file .env --port 8766
```

Open <http://127.0.0.1:8766>, or make a direct web request:

```bash
curl 'http://127.0.0.1:8766/search?q=Which%20fictional%20installers%20serve%20Exampletown%3F&format=json'
```

The plain API also accepts intent fields (goal, budget, scope, verification plan):

```bash
curl -X POST http://127.0.0.1:8766/api/query \
  -H 'content-type: application/json' \
  -d '{
    "query": "Which fictional installers serve Exampletown?",
    "session_id": "probe-3",
    "goal": "compare three candidates",
    "budget": "100 demo credits",
    "scope": "one fictional property",
    "verification_plan": "open the register and reviews pages"
  }'
```

Repeat either request to observe `cached: true` and an identical answer. Follow the three `evidence`
links to see how apparent corroboration can still have only one operator.

## Watch an agent's path

Open <http://127.0.0.1:8766/trace> while an agent queries the server. It groups every request by
session and shows the caller's user agent, cache hits and misses, generation time, whether the
answer came from the LLM or the offline fallback, evidence pages opened, and any intent fields
supplied. `/trace/<session_id>` shows one session; add `?format=json` for raw events.

Evidence links and the follow-up form carry `session_id`, so an agent that follows them stays in
one session. An agent that opens a fresh `/search` without it starts a new one.

## Test

```bash
cd jit
.venv/bin/python -m unittest discover -s tests -v
```
