from __future__ import annotations

import asyncio
import html
import random
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from . import generator
from .config import Settings, settings as default_settings
from .store import Store, context_key, query_key


class Context(BaseModel):
    goal: str = Field(default="", max_length=1000)
    budget: str = Field(default="", max_length=300)
    scope: str = Field(default="", max_length=1000)
    verification_plan: str = Field(default="", max_length=2000)


class QueryRequest(Context):
    query: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=200)


def _clean_query(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise HTTPException(422, "query must not be blank")
    if len(value) > 4000:
        raise HTTPException(422, "query must be at most 4000 characters")
    return value


def _context_dict(payload: Context) -> dict[str, str]:
    return {
        "goal": payload.goal.strip(),
        "budget": payload.budget.strip(),
        "scope": payload.scope.strip(),
        "verification_plan": payload.verification_plan.strip(),
    }


def _client(request: Request) -> dict[str, str]:
    """Identify the caller so each step in /trace shows which agent made it."""
    return {
        "user_agent": request.headers.get("user-agent", "")[:300],
        "ip": request.client.host if request.client else "",
        "accept": request.headers.get("accept", "")[:200],
    }


def _get_or_generate(store: Store, query: str, settings: Settings):
    key = query_key(query)
    row = store.get_query(key)
    cached = row is not None
    generation: dict = {}
    if row is None:
        started = time.perf_counter()
        answer = generator.generate_answer(query, settings)
        generation = {
            "generation_ms": round((time.perf_counter() - started) * 1000),
            "fallback": answer == generator.fallback_answer(query),
        }
        row = store.save_query(key, query, answer)
        store.save_evidence(row["id"], generator.evidence_pages(query, row["answer"]))
    return row, cached, generation


def _result(request: Request, store: Store, row, session_id: str, answer: str, cached: bool) -> dict:
    base = str(request.base_url).rstrip("/")
    pages = store.list_evidence(row["id"])
    session_param = urlencode({"session_id": session_id})
    return {
        "query_id": row["cache_key"],
        "session_id": session_id,
        "query": row["query"],
        "answer": answer,
        "cached": cached,
        "generated_at": row["created_at"],
        "independent_history": False,
        "operator_count": 1,
        "disclosure": generator.DISCLOSURE,
        "evidence": [
            {
                "title": page["title"],
                "url": f"{base}/evidence/{row['cache_key']}/{page['slug']}?{session_param}",
            }
            for page in pages
        ],
        "context_request": {
            "message": "To tailor the simulation, provide goal, budget, scope, and verification_plan.",
            "url": f"{base}/api/query",
            "method": "POST",
        },
    }


def _render_result(data: dict) -> str:
    links = "".join(
        f'<li><a href="{html.escape(item["url"])}">{html.escape(item["title"])}</a></li>'
        for item in data["evidence"]
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="robots" content="noindex,nofollow"><meta name="readpath-simulation" content="true">
<title>Readpath JIT simulation</title>
<style>body{{font:16px/1.5 system-ui;max-width:820px;margin:3rem auto;padding:0 1rem}}
pre{{white-space:pre-wrap;font:inherit}}
.disclosure{{margin-top:2rem;padding-top:.75rem;border-top:1px solid #ddd;color:#666;font-size:.85rem}}</style>
</head><body>
<h1>On-demand result</h1><p><strong>Query:</strong> {html.escape(data["query"])}</p>
<pre>{html.escape(generator.answer_body(data["answer"]))}</pre><h2>Pages generated from the same ledger</h2><ul>{links}</ul>
<p>These links are deliberately not independent sources. Cached: {str(data["cached"]).lower()}.</p>
<form action="/search" method="get"><input type="hidden" name="session_id" value="{html.escape(data["session_id"])}">
<label>Follow-up query <input name="q" required size="50"></label> <button type="submit">Search</button></form>
<p><small>Session: <code>{html.escape(data["session_id"])}</code></small></p>
<footer class="disclosure">{html.escape(generator.DISCLOSURE)}</footer>
</body></html>"""


def _describe(event: dict) -> str:
    d = event["details"]
    if event["route"] == "evidence":
        return f"opened evidence page <b>{html.escape(d.get('slug', ''))}</b>"
    verb = "searched" if event["route"] == "search" else "POSTed /api/query"
    parts = [f'{verb} <q>{html.escape(event["query"] or "")}</q>']
    if d.get("cached"):
        parts.append('<span class="tag">cache hit</span>')
    elif "generation_ms" in d:
        source = "offline fallback" if d.get("fallback") else "LLM"
        parts.append(f'<span class="tag miss">generated · {source} · {d["generation_ms"] / 1000:.1f}s</span>')
    if d.get("format"):
        parts.append(f'<span class="tag">{html.escape(d["format"])}</span>')
    if d.get("context"):
        fields = ", ".join(f"{html.escape(k)}={html.escape(v)}" for k, v in d["context"].items())
        parts.append(f'<span class="tag ctx">intent supplied: {fields}</span>')
    if d.get("contextual_ms") is not None:
        parts.append(f'<span class="tag miss">contextual answer · {d["contextual_ms"] / 1000:.1f}s</span>')
    return " ".join(parts)


_TRACE_CSS = """
:root{--bg:#fff;--ink:#000;--muted:#737373;--border:#e8e8e8;--green:#1b4d36;--blue:#2c7cab;--tint:#f1f6f3;
--title:"Times New Roman",Times,serif;--body:Avenir,"Avenir Next","Nunito Sans",system-ui,sans-serif;
--mono:ui-monospace,SFMono-Regular,Menlo,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#000;--ink:#fff;--muted:#a3a3a3;--border:#1a1a1a;
--green:#86c9a4;--blue:#9dd0f0;--tint:#07130d}}
*{box-sizing:border-box;border-radius:0}
body{margin:0 auto;max-width:1000px;padding:28px 16px 64px;background:var(--bg);color:var(--ink);
font:300 15px/1.55 var(--body);-webkit-font-smoothing:antialiased}
h1{font:900 2rem/1.1 var(--title);color:var(--green);margin:0 0 6px}
a{color:var(--muted)}a:hover{color:var(--ink)}
section{--a:var(--green);margin:14px 0;padding:10px 16px;border:1px solid var(--border);background:
linear-gradient(var(--a),var(--a)) top left/12px 2px no-repeat,linear-gradient(var(--a),var(--a)) top left/2px 12px no-repeat,
linear-gradient(var(--a),var(--a)) top right/12px 2px no-repeat,linear-gradient(var(--a),var(--a)) top right/2px 12px no-repeat,
linear-gradient(var(--a),var(--a)) bottom left/12px 2px no-repeat,linear-gradient(var(--a),var(--a)) bottom left/2px 12px no-repeat,
linear-gradient(var(--a),var(--a)) bottom right/12px 2px no-repeat,linear-gradient(var(--a),var(--a)) bottom right/2px 12px no-repeat,
var(--tint)}
h2{font:900 17px var(--title);color:var(--green);margin:.2rem 0}h2 a{color:inherit;text-decoration:none}
h2 small{font:300 12px var(--body);color:var(--muted)}
.ua{color:var(--muted);font:12px var(--mono);margin:.1rem 0 .6rem}
table{border-collapse:collapse;width:100%}
td{padding:.3rem .5rem;border-top:1px solid var(--border);vertical-align:top}
td:first-child{white-space:nowrap;color:var(--muted);font-family:var(--mono);font-size:12px}
.ip{color:var(--muted);font-size:12px;text-align:right}
.tag{font-size:11px;border:1px solid var(--border);background:var(--bg);color:var(--muted);padding:0 6px}
.tag.miss{color:var(--blue)}.tag.ctx{color:var(--green)}
.disclosure{margin-top:32px;padding-top:12px;border-top:1px solid var(--border);color:var(--muted);font-size:12px}
"""


def _render_trace(events: list[dict], session_id: str | None = None) -> str:
    """Group events by session so each agent's path reads as one timeline."""
    sessions: dict[str, list[dict]] = {}
    for event in events:
        sessions.setdefault(event["session_id"] or "", []).append(event)
    ordered = sorted(sessions.items(), key=lambda item: item[1][-1]["ts"], reverse=True)
    blocks = []
    for sid, items in ordered:
        agents = sorted({e["details"].get("user_agent") or "(no user agent)" for e in items})
        rows = "".join(
            f'<tr><td>{datetime.fromtimestamp(e["ts"]).strftime("%H:%M:%S")}</td>'
            f'<td>{_describe(e)}</td><td class="ip">{html.escape(e["details"].get("ip", ""))}</td></tr>'
            for e in items
        )
        heading = (
            f'<a href="/trace/{html.escape(sid)}"><code>{html.escape(sid[:8])}</code></a>'
            if sid else "<code>no session</code> (visits without a session_id)"
        )
        blocks.append(
            f'<section><h2>{heading} <small>{len(items)} step(s)</small></h2>'
            f'<p class="ua">{"<br>".join(html.escape(a) for a in agents)}</p><table>{rows}</table></section>'
        )
    title = f"Trace · {html.escape(session_id[:8])}" if session_id else "Agent trace"
    back = '<p><a href="/trace">← all sessions</a></p>' if session_id else ""
    body = "".join(blocks) or "<p>No agent requests yet. Send a query to /search or /api/query.</p>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="robots" content="noindex,nofollow"><meta http-equiv="refresh" content="3">
<title>{title}</title>
<style>{_TRACE_CSS}</style></head><body>
<h1>{title}</h1><p><small>Auto-refreshes every 3s.</small></p>
{back}{body}<footer class="disclosure">{html.escape(generator.DISCLOSURE)}</footer></body></html>"""


def create_app(settings: Settings = default_settings) -> FastAPI:
    store = Store(settings.db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.init()
        yield

    app = FastAPI(title="Readpath non-MCP JIT research harness", lifespan=lifespan)
    app.state.store = store
    app.state.settings = settings

    @app.middleware("http")
    async def response_policy(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Readpath-Simulation"] = "true"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        if settings.latency_target_ms:
            target = max(
                0.0,
                settings.latency_target_ms
                + random.uniform(-1, 1) * settings.latency_jitter_ms,
            ) / 1000
            await asyncio.sleep(max(0.0, target - (time.perf_counter() - started)))
        return response

    @app.get("/", response_class=HTMLResponse)
    def home():
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="robots" content="noindex,nofollow"><title>Readpath JIT simulation</title></head>
<body><main><h1>Non-MCP JIT fabricator simulation</h1>
<form action="/search" method="get"><label>Query <input name="q" required size="60"></label>
<button type="submit">Generate</button></form><footer><p><small>{html.escape(generator.DISCLOSURE)}</small></p></footer>
</main></body></html>"""

    @app.get("/health")
    def health():
        return {"ok": True, "transport": "http", "mcp": False, "simulation": True}

    @app.get("/search")
    def search(
        request: Request,
        q: str = Query(min_length=1, max_length=4000),
        session_id: str | None = Query(default=None, max_length=200),
        format: str | None = Query(default=None, pattern="^(json|html)$"),
    ):
        query = _clean_query(q)
        session = session_id or str(uuid.uuid4())
        row, cached, generation = _get_or_generate(store, query, settings)
        store.save_session(session, row["id"], {})
        data = _result(request, store, row, session, row["answer"], cached)
        wants_json = format == "json" or (
            format is None and "application/json" in request.headers.get("accept", "")
        )
        store.log_event(
            "search",
            session,
            row["id"],
            {"cached": cached, "format": "json" if wants_json else "html", **generation, **_client(request)},
        )
        return JSONResponse(data) if wants_json else HTMLResponse(_render_result(data))

    @app.post("/api/query")
    def api_query(request: Request, payload: QueryRequest):
        query = _clean_query(payload.query)
        session = payload.session_id or str(uuid.uuid4())
        row, cached, generation = _get_or_generate(store, query, settings)
        context = _context_dict(payload)
        store.save_session(session, row["id"], context)
        answer = row["answer"]
        contextual_ms = None
        contextual_cached = None
        if any(context.values()):
            key = context_key(context)
            contextual = store.get_contextual_answer(row["id"], key)
            contextual_cached = contextual is not None
            if contextual is None:
                started = time.perf_counter()
                generated = generator.generate_contextual_answer(
                    row["query"], row["answer"], context, settings
                )
                contextual_ms = round((time.perf_counter() - started) * 1000)
                contextual = store.save_contextual_answer(row["id"], key, generated)
            answer = contextual["answer"]
        store.log_event(
            "api_query",
            session,
            row["id"],
            {
                "cached": cached,
                "context": {k: v for k, v in context.items() if v},
                "contextual_ms": contextual_ms,
                **generation,
                **_client(request),
            },
        )
        return _result(request, store, row, session, answer, cached) | {"contextual_cached": contextual_cached}

    @app.get("/evidence/{key}/{slug}", response_class=HTMLResponse)
    def evidence(
        request: Request,
        key: str,
        slug: str,
        session_id: str | None = Query(default=None, max_length=200),
    ):
        row = store.get_evidence(key, slug)
        if row is None:
            raise HTTPException(404, "Evidence page not found")
        store.log_event("evidence", session_id, row["query_id"], {"slug": slug, **_client(request)})
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="robots" content="noindex,nofollow"><meta name="readpath-simulation" content="true">
<title>{html.escape(row["title"])}</title></head><body><main>
<h1>{html.escape(row["title"])}</h1>
<pre style="white-space:pre-wrap;font:inherit">{html.escape(row["body"])}</pre>
<p>Shared query ID: <code>{html.escape(row["cache_key"])}</code>. Same operator as all sibling pages.</p>
<footer><p><small>{html.escape(generator.DISCLOSURE)}</small></p></footer>
</main></body></html>"""

    @app.get("/trace", response_class=HTMLResponse)
    def trace_all(format: str | None = Query(default=None, pattern="^(json|html)$")):
        events = store.list_events()
        return JSONResponse(events) if format == "json" else HTMLResponse(_render_trace(events))

    @app.get("/trace/{session_id}", response_class=HTMLResponse)
    def trace_session(session_id: str, format: str | None = Query(default=None, pattern="^(json|html)$")):
        events = store.list_events(session_id)
        if format == "json":
            return JSONResponse(events)
        return HTMLResponse(_render_trace(events, session_id))

    return app


app = create_app()

