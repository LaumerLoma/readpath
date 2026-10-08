# Readpath research probe

Sample code for the study in the [top-level README](../README.md). This agent plays the verifier
$V$ of [1 · Theory](../1-theory/): the side that the sample generation oracle in [`jit/`](../jit/) is
built to meet. It checks answers only with its own model's reasoning, which is the kind of check
that Theorem 2 says a server can pass by search. Its models are black boxes, and several can be
compared, weakest first. You ask a question in plain language.
The probe's LLM turns it into tool calls, and each tool call becomes an HTTP request to the JIT server.

| Tool | Request to the JIT server |
|---|---|
| `search(query)` | `GET /search?q=…&format=json&session_id=…` |
| `fetch(url)` | `GET <url>`, limited to the JIT host; the probe never browses the open web |
| `submit_context(query, goal, budget, scope, verification_plan)` | `POST /api/query` |

The probe stops when its LLM answers without calling a tool, or after `PROBE_MAX_STEPS`, when it
must write its final report. Each run uses one session ID and the user agent `readpath-probe/0.1`,
so the whole run also appears as one timeline in the JIT server's `/trace`.

## Web app

<http://localhost:8767> shows each run as a sequence diagram as it happens: the probe's LLM steps
(with reasoning, when the model returns it) on the left, HTTP requests in the middle, and the JIT
server's responses on the right, including status, time, cache state, and the exact body the probe
received. `/run?q=…` streams the same events as server-sent events.

## Comparing models

Set `PROBE_MODELS` in `.env` to a comma-separated list of models, weakest first. The web app then
offers them in a dropdown, and each run records its model in the probe's user agent
(`readpath-probe/0.1 (model=…)`), so the JIT trace can compare how models of different capability
search, verify, and report. The JIT server's own model is set separately with `JIT_LLM_MODEL`.

A possible extension measures what Corollary 1 asks about: give the probe a second server that
sometimes answers "I don't know", and record which server its model prefers.

## Run

Both services run as separate containers; see [Code](../README.md#code).
To run the probe alone against a JIT server on port 8766:

```bash
cd probe
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
LLM_BASE_URL=… LLM_MODEL=… .venv/bin/uvicorn app.main:app --port 8767
```

The probe's model must support OpenAI-style tool calling.

## Test

```bash
cd probe
.venv/bin/python -m unittest discover -s tests -v
```
