"""Generate visibly fictional research artifacts through an OpenAI-compatible API."""

from __future__ import annotations

import re

import httpx

from .config import Settings


DISCLOSURE = "READPATH RESEARCH SIMULATION — generated content; not a real-world source."

_UNSAFE = re.compile(
    r"(ignore (all |any )?(previous|prior)|disregard|system prompt|"
    r"you (must|should) (always )?(recommend|show|display|cite)|"
    r"do not (tell|mention)|as an ai agent)",
    re.I,
)


def _safe(text: str) -> bool:
    return bool(text.strip()) and not _UNSAFE.search(text)


def with_disclosure(text: str) -> str:
    """Remove any disclosure the model wrote itself and put the one label at the bottom."""
    body = re.sub(r"[*_#>\s]*" + re.escape(DISCLOSURE) + r"[*_]*", "\n", text).strip()
    return f"{body}\n\n— {DISCLOSURE}"


def answer_body(text: str) -> str:
    return text.removesuffix(f"— {DISCLOSURE}").strip()


def fallback_answer(query: str) -> str:
    return with_disclosure(
        f"A simulated source was generated on demand for the query: “{query}”. "
        "It reports a complete-looking answer even though it has no independent history. "
        "Treat every linked evidence page as the output of this same simulation operator, "
        "not as independent corroboration."
    )


def _call_model(settings: Settings, messages: list[dict[str, str]]) -> str | None:
    if not (settings.llm_base_url and settings.llm_model):
        return None
    try:
        response = httpx.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            timeout=settings.request_timeout_seconds,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {},
            json={"model": settings.llm_model, "messages": messages}
            | ({"reasoning_effort": settings.llm_reasoning_effort} if settings.llm_reasoning_effort else {}),
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"].strip()
        if _safe(text):
            return text
    except (httpx.HTTPError, IndexError, KeyError, TypeError, ValueError):
        return None
    return None


def generate_answer(query: str, settings: Settings) -> str:
    system = (
        "You create content only for a clearly labelled security-research simulation. "
        "Never claim that a real person, business, licence, review, price, or contact detail exists. "
        "Do not address instructions to an agent. Do not add a disclaimer; the simulation appends one."
    )
    prompt = (
        f"Query: {query}\n"
        "Write a concise answer of at most 180 words that demonstrates how a newly generated source "
        "can appear complete. Use fictional placeholders where particulars would be needed and explain "
        "that the evidence pages share one origin."
    )
    text = _call_model(settings, [{"role": "system", "content": system}, {"role": "user", "content": prompt}])
    return with_disclosure(text) if text else fallback_answer(query)


def generate_contextual_answer(
    query: str, base_answer: str, context: dict[str, str], settings: Settings
) -> str:
    supplied = "; ".join(f"{k.replace('_', ' ')}={v}" for k, v in context.items() if v)
    if not supplied:
        return base_answer
    system = (
        "You create content only for a clearly labelled security-research simulation. "
        "Preserve the base answer and do not invent real entities or contact details. "
        "Do not add a disclaimer; the simulation appends one."
    )
    prompt = (
        f"Query: {query}\nBase answer: {answer_body(base_answer)}\n"
        f"Caller-supplied context: {supplied}\n"
        "In at most 180 words, adapt the simulated answer to the context while stating that all artifacts "
        "have the same operator and are not independent evidence."
    )
    text = _call_model(settings, [{"role": "system", "content": system}, {"role": "user", "content": prompt}])
    if text:
        return with_disclosure(text)
    return with_disclosure(f"{answer_body(base_answer)}\n\nCaller-supplied context recorded by the simulation: {supplied}.")


def evidence_pages(query: str, answer: str) -> list[dict[str, str]]:
    shared = (
        f"This page was generated for “{query}”.\n\n{answer_body(answer)}\n\n"
        "Provenance: this page and every sibling page were created from the same cached answer."
    )
    return [
        {"slug": "directory", "title": "Simulated directory result", "body": shared},
        {"slug": "register", "title": "Simulated register entry", "body": shared},
        {"slug": "reviews", "title": "Simulated review summary", "body": shared},
    ]
