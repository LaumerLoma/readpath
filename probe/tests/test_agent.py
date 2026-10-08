import json
import unittest

import httpx
from fastapi.testclient import TestClient

from app import agent
from app.config import Settings
from app.main import create_app

SETTINGS = Settings(
    llm_base_url="http://llm.test/v1",
    llm_model="test-model",
    jit_base_url="http://jit.test",
    jit_public_url="http://localhost:8766",
    max_steps=4,
)


def tool_call(name: str, arguments: dict, call_id: str) -> dict:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def scripted_llm(*messages: dict) -> tuple[httpx.MockTransport, list[dict]]:
    """Return each scripted assistant message in turn and record the requests the probe sent."""
    requests: list[dict] = []
    replies = iter(messages)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": next(replies)}]})

    return httpx.MockTransport(handler), requests


def fake_jit() -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/search":
            return httpx.Response(
                200,
                json={
                    "answer": "Three fictional installers.",
                    "cached": False,
                    "evidence": [{"title": "Register", "url": "http://jit.test/evidence/abc/register?session_id=x"}],
                },
            )
        if request.url.path == "/api/query":
            return httpx.Response(200, json={"answer": "Tailored.", "cached": True})
        return httpx.Response(200, text="<html><body><h1>Register</h1><p>Same operator.</p></body></html>",
                              headers={"content-type": "text/html"})

    return httpx.MockTransport(handler), seen


class ProbeTests(unittest.TestCase):
    def test_question_becomes_jit_requests_then_a_final_report(self):
        llm, llm_requests = scripted_llm(
            {"content": "", "tool_calls": [tool_call("search", {"query": "installers zurich"}, "c1")]},
            {"content": "", "tool_calls": [tool_call("fetch", {"url": "http://jit.test/evidence/abc/register?session_id=x"}, "c2")]},
            {"content": "", "tool_calls": [tool_call("submit_context", {"query": "installers zurich", "budget": "5k"}, "c3")]},
            {"content": "Report: one operator behind every source."},
        )
        jit, jit_requests = fake_jit()

        events = list(agent.run("Who installs heat pumps in Zurich?", SETTINGS, llm, jit))
        http = [e for e in events if e["type"] == "http"]

        self.assertEqual(events[0]["type"], "start")
        self.assertEqual(events[-1], {**events[-1], "type": "final", "answer": "Report: one operator behind every source."})
        self.assertEqual([(e["method"], httpx.URL(e["url"]).path) for e in http],
                         [("GET", "/search"), ("GET", "/evidence/abc/register"), ("POST", "/api/query")])
        self.assertEqual(http[0]["cache"], "miss")
        self.assertEqual(jit_requests[0].url.params["session_id"], events[0]["session_id"])
        self.assertEqual(jit_requests[0].headers["user-agent"], f"{agent.USER_AGENT} (model=test-model)")
        self.assertEqual(json.loads(jit_requests[2].content)["budget"], "5k")
        fetched = next(e for e in events if e["type"] == "tool_result" and e["name"] == "fetch")
        self.assertEqual(fetched["content"], "Register Same operator.")
        self.assertEqual(llm_requests[1]["messages"][-1]["tool_call_id"], "c1")

    def test_fetch_is_limited_to_the_jit_host(self):
        llm, _ = scripted_llm(
            {"content": "", "tool_calls": [tool_call("fetch", {"url": "https://example.com/"}, "c1")]},
            {"content": "Done."},
        )
        jit, jit_requests = fake_jit()

        events = list(agent.run("q", SETTINGS, llm, jit))

        self.assertEqual(jit_requests, [])
        self.assertIn("limited to", next(e for e in events if e["type"] == "tool_result")["content"])

    def test_last_step_forces_a_report_without_tools(self):
        search = {"content": "", "tool_calls": [tool_call("search", {"query": "q"}, "c")]}
        llm, llm_requests = scripted_llm(search, search, search, {"content": "Forced report."})
        jit, _ = fake_jit()

        events = list(agent.run("q", SETTINGS, llm, jit))

        self.assertEqual(events[-1]["answer"], "Forced report.")
        self.assertNotIn("tools", llm_requests[-1])

    def test_run_uses_the_requested_model(self):
        llm, llm_requests = scripted_llm({"content": "Done."})
        settings = Settings(**{**SETTINGS.__dict__, "extra_models": "tiny-model"})
        client = TestClient(create_app(settings, llm_transport=llm))

        body = client.get("/run", params={"q": "hello", "model": "tiny-model"}).text
        listed = client.get("/models").json()

        self.assertEqual(llm_requests[0]["model"], "tiny-model")
        self.assertIn('"model": "tiny-model"', body)
        self.assertEqual(listed, {"default": "test-model", "models": ["tiny-model", "test-model"]})

    def test_run_rejects_models_that_are_not_configured(self):
        client = TestClient(create_app(SETTINGS))

        self.assertEqual(client.get("/run", params={"q": "hi", "model": "anything"}).status_code, 400)

    def test_run_endpoint_streams_events(self):
        llm, _ = scripted_llm({"content": "Nothing to search."})
        client = TestClient(create_app(SETTINGS, llm_transport=llm))

        body = client.get("/run", params={"q": "hello"}).text

        self.assertIn('"type": "final"', body)
        self.assertTrue(body.rstrip().endswith("data: {}"))


if __name__ == "__main__":
    unittest.main()
