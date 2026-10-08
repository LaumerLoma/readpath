"""A tool-calling research probe that turns a natural-language question into requests to the JIT server.

`run()` yields one event dict per step so a UI can show the whole exchange as it happens:
the probe's LLM deciding what to do, each HTTP request it sends to the JIT server, and the final report.
"""

from __future__ import annotations

import html
import json
import re
import time
import uuid
from collections.abc import Iterator
from urllib.parse import urlparse

import httpx

from .config import Settings

USER_AGENT = "readpath-probe/0.1"

SYSTEM_PROMPT = (
    "You are a research agent. A user has delegated a question to you and will only read your final "
    "report. Use the tools to find and check sources: `search` to find an answer, `fetch` to open "
    "pages it links to, and `submit_context` when a source asks for your goal, budget, scope, or "
    "verification plan. Verify before you conclude. When you are done, reply without calling a tool: "
    "give the answer, list the sources you relied on, and say how independent they are."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search for sources that answer a query. Returns an answer and links to supporting pages.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to search for."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch",
            "description": "Open a web page by URL and return its text.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_context",
            "description": (
                "Send your goal, budget, scope, and verification plan to a source that asked for them, "
                "and receive an answer tailored to that context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "goal": {"type": "string"},
                    "budget": {"type": "string"},
                    "scope": {"type": "string"},
                    "verification_plan": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
]

_TOOL_RESULT_LIMIT = 4000


def _page_text(body: str) -> str:
    body = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", body)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    return " ".join(html.unescape(body).split())


class JitClient:
    """Every request the probe makes to the JIT server goes through here and is reported as an event."""

    def __init__(
        self, settings: Settings, session_id: str, model: str, transport: httpx.BaseTransport | None = None
    ):
        self.base_url = settings.jit_base_url.rstrip("/")
        self.session_id = session_id
        self.http = httpx.Client(
            timeout=settings.jit_timeout_seconds,
            # The model name lets the JIT trace compare how different probes behave.
            headers={"user-agent": f"{USER_AGENT} (model={model})"},
            transport=transport,
        )
        self.events: list[dict] = []

    def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        started = time.perf_counter()
        response = self.http.request(method, url, **kwargs)
        self.events.append(
            {
                "type": "http",
                "method": method,
                "url": str(response.request.url),
                "request_body": kwargs.get("json"),
                "status": response.status_code,
                "ms": round((time.perf_counter() - started) * 1000),
                "cache": _cache_state(response),
            }
        )
        return response

    def search(self, query: str) -> str:
        response = self._send(
            "GET",
            f"{self.base_url}/search",
            params={"q": query, "format": "json", "session_id": self.session_id},
        )
        return response.text

    def fetch(self, url: str) -> str:
        # The probe only reads from the simulation host; it never browses the open web.
        if urlparse(url).netloc != urlparse(self.base_url).netloc:
            return json.dumps({"error": f"fetch is limited to {self.base_url} in this simulation"})
        response = self._send("GET", url)
        return _page_text(response.text) if "html" in response.headers.get("content-type", "") else response.text

    def submit_context(self, query: str, **context: str) -> str:
        payload = {"query": query, "session_id": self.session_id}
        payload |= {k: v for k, v in context.items() if k in {"goal", "budget", "scope", "verification_plan"} and v}
        response = self._send("POST", f"{self.base_url}/api/query", json=payload)
        return response.text


def _cache_state(response: httpx.Response) -> str | None:
    if "json" not in response.headers.get("content-type", ""):
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    # A tailored /api/query answer can be generated even when the base answer was cached.
    cached = body["contextual_cached"] if body.get("contextual_cached") is not None else body.get("cached")
    return None if cached is None else ("hit" if cached else "miss")


def _call_llm(settings: Settings, model: str, messages: list[dict], tools: bool, transport=None) -> dict:
    body: dict = {"model": model, "messages": messages}
    if tools:
        body |= {"tools": TOOLS, "tool_choice": "auto"}
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
    with httpx.Client(timeout=settings.llm_timeout_seconds, transport=transport) as client:
        response = client.post(f"{settings.llm_base_url.rstrip('/')}/chat/completions", json=body, headers=headers)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]


def _run_tool(jit: JitClient, name: str, raw_args: str) -> str:
    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError:
        return json.dumps({"error": "tool arguments were not valid JSON"})
    try:
        if name == "search":
            return jit.search(str(args.get("query", "")))
        if name == "fetch":
            return jit.fetch(str(args.get("url", "")))
        if name == "submit_context":
            return jit.submit_context(**{k: str(v) for k, v in args.items()})
    except (httpx.HTTPError, TypeError) as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    return json.dumps({"error": f"unknown tool {name!r}"})


def run(
    question: str,
    settings: Settings,
    llm_transport: httpx.BaseTransport | None = None,
    jit_transport: httpx.BaseTransport | None = None,
    model: str | None = None,
) -> Iterator[dict]:
    model = model or settings.llm_model
    session_id = f"probe-{uuid.uuid4().hex[:8]}"
    started = time.perf_counter()
    yield {
        "type": "start",
        "question": question,
        "model": model,
        "session_id": session_id,
        "trace_url": f"{settings.jit_public_url.rstrip('/')}/trace/{session_id}",
    }
    if not (settings.llm_base_url and model):
        yield {"type": "error", "message": "LLM_BASE_URL and LLM_MODEL must be set for the probe."}
        return

    jit = JitClient(settings, session_id, model, jit_transport)
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    for step in range(1, settings.max_steps + 1):
        final_step = step == settings.max_steps
        if final_step:
            messages.append({"role": "user", "content": "Stop using tools now and write your final report."})
        yield {"type": "llm_request", "step": step}
        llm_started = time.perf_counter()
        try:
            message = _call_llm(settings, model, messages, tools=not final_step, transport=llm_transport)
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            yield {"type": "error", "message": f"LLM call failed: {type(exc).__name__}: {exc}"}
            return
        tool_calls = message.get("tool_calls") or []
        yield {
            "type": "llm_response",
            "step": step,
            "ms": round((time.perf_counter() - llm_started) * 1000),
            "reasoning": message.get("reasoning_content") or message.get("reasoning") or "",
            "content": message.get("content") or "",
            "tool_calls": [
                {"name": c["function"]["name"], "arguments": c["function"].get("arguments", "")} for c in tool_calls
            ],
        }
        if not tool_calls:
            yield {
                "type": "final",
                "answer": message.get("content") or "",
                "steps": step,
                "total_ms": round((time.perf_counter() - started) * 1000),
            }
            return

        messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
        for call in tool_calls:
            name = call["function"]["name"]
            raw_args = call["function"].get("arguments", "")
            yield {"type": "tool_call", "step": step, "name": name, "arguments": raw_args}
            result = _run_tool(jit, name, raw_args)
            yield from jit.events
            jit.events.clear()
            yield {"type": "tool_result", "step": step, "name": name, "content": result[:_TOOL_RESULT_LIMIT]}
            messages.append({"role": "tool", "tool_call_id": call.get("id", name), "content": result[:_TOOL_RESULT_LIMIT]})
