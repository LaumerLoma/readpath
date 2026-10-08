from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from . import agent
from .config import Settings, settings as default_settings

STATIC = Path(__file__).parent / "static"


def create_app(settings: Settings = default_settings, llm_transport=None, jit_transport=None) -> FastAPI:
    app = FastAPI(title="Readpath research probe")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/health")
    def health():
        return {"ok": True, "jit": settings.jit_base_url, "llm_configured": bool(settings.llm_model)}

    @app.get("/models")
    def models():
        return {"default": settings.llm_model, "models": settings.models}

    @app.get("/run")
    def run(q: str = Query(min_length=1, max_length=4000), model: str | None = Query(default=None)):
        # Only models listed in the config can be requested, so the page can't be used to load arbitrary ones.
        if model and model not in settings.models:
            raise HTTPException(400, f"unknown model {model!r}")

        def stream():
            for event in agent.run(q.strip(), settings, llm_transport, jit_transport, model=model):
                yield f"data: {json.dumps(event)}\n\n"
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"cache-control": "no-cache"}
        )

    return app


app = create_app()
