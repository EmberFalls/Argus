from __future__ import annotations

import asyncio
import hashlib

from argus_contracts.models import BindingResult, ElementCatalogEntry, Evidence, Spec, Step, TestCase
from argus.supervisor import loop as supervisor


def test_live_pipeline_parses_generates_binds_and_persists_cases(tmp_path, monkeypatch):
    parsed_case = TestCase(id="journey-login", journey="Log in", description="Log in",
                           steps=[Step(action="click", locator="role=button[name=Log in]")])
    playbook_case = TestCase(id="playbook-boundary", journey="Input boundary",
                             description="Check an input boundary",
                             steps=[Step(action="fill", locator="role=textbox[name=Email]", value="x")],
                             category="edge_case", source="playbook")
    parsed_spec = Spec(description="A sign-in app", journeys=[parsed_case])
    element = ElementCatalogEntry(id="login", role="button", name="Log in",
                                  semantic_locator='role=button[name="Log in"]',
                                  visible=True, enabled=True, in_viewport=True)
    calls = {}

    class FakePage:
        url = "https://example.test"

        async def goto(self, *args, **kwargs):
            return None

    class FakeSession:
        page = FakePage()

        async def close(self):
            return None

    class FakeBrowserFactory:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def new_context(self, *args, **kwargs):
            return FakeSession(), None

    class FakeGateway:
        pass

    async def fake_explore(page):
        return "a11y snapshot", [element]

    async def fake_parse(description, *, context, gateway, run_id):
        calls["parser"] = (description, context, gateway, run_id)
        return parsed_spec

    def fake_playbook(spec, elements):
        assert spec is parsed_spec
        assert elements == [element]
        return [playbook_case]

    async def fake_bind(cases, elements, *, gateway, run_id):
        calls["binding_cases"] = list(cases)
        assert gateway is calls["parser"][2]
        return [
            BindingResult(test_case=cases[0], verdict="BOUND", deterministic_steps=[0]),
            BindingResult(test_case=cases[1], verdict="INCONCLUSIVE", reason="No safe target"),
        ]

    async def fake_execute(session, case, layout, *, initial_url):
        calls.setdefault("executed", []).append(case.id)
        return "PASS", Evidence(steps=case.steps, expected=case.expected, actual="ok"), 12

    monkeypatch.setattr(supervisor, "BrowserSessionFactory", FakeBrowserFactory)
    monkeypatch.setattr(supervisor, "ModelGateway", FakeGateway)
    monkeypatch.setattr(supervisor, "explore", fake_explore)
    monkeypatch.setattr(supervisor, "parse_spec", fake_parse)
    monkeypatch.setattr(supervisor, "generate_playbook", fake_playbook)
    monkeypatch.setattr(supervisor, "bind_cases", fake_bind)
    monkeypatch.setattr(supervisor, "execute_case", fake_execute)

    async def scenario():
        return await supervisor.run_qa("https://example.test", "A sign-in app", output_dir=tmp_path,
                                       spec_context={"README.md": "Login is supported."})

    result = asyncio.run(scenario())
    assert calls["parser"][1] == {"README.md": "Login is supported."}
    assert [case.id for case in calls["binding_cases"]] == ["journey-login", "playbook-boundary"]
    assert calls["executed"] == ["journey-login"]
    assert [item["verdict"] for item in result["test_results"]] == ["PASS", "INCONCLUSIVE"]
    assert [case["id"] for case in result["test_cases"]] == ["journey-login", "playbook-boundary"]
    assert result["parsed_spec"]["description"] == "A sign-in app"
    assert result["exported_tests"] == ["tests/case-" + hashlib.sha256(b"journey-login").hexdigest()[:24] + ".spec.ts"]
    exported = tmp_path / "runs" / result["run_id"] / result["exported_tests"][0]
    assert "ARGUS_BASE_URL" in exported.read_text(encoding="utf-8")
