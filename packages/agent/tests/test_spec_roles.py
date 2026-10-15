from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from argus.models import MalformedModelResponse, ModelGateway, ModelRoute, ModelSettings, TIERS
from argus.spec.binder import _action_compatible, bind_cases
from argus.spec.parser import claim_id, parse_spec
from argus.spec.playbook import generate, registered_checks
from argus.agents.tester import _run_step
from argus_contracts.models import ElementCatalogEntry, Spec, Step, TestCase


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures"


def _spec_response() -> dict:
    response = json.loads((FIXTURES / "spec.json").read_text(encoding="utf-8"))
    titles = ["Sign up", "Log in", "Create an article", "Favorite an article",
              "Comment on an article", "Update a profile"]
    template = response["journeys"][0]
    response["journeys"] = [
        {**template, "id": f"journey-{index:02d}", "journey": title,
         "description": f"Verify the {title.lower()} flow."}
        for index, title in enumerate(titles, 1)
    ]
    response["claims"][0]["id"] = "model-generated-id"
    response["claims"][0]["journey_ids"] = ["journey-01", "unknown-journey"]
    response["claims"].append({
        **response["claims"][0],
        "id": "duplicate-claim-id",
        "statement": " favoriting an article increments its count exactly once. ",
        "journey_ids": ["journey-02"],
    })
    return response


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.requests = []

    async def generate(self, **kwargs):
        self.calls += 1
        self.requests.append(kwargs)
        response = self.responses.pop(0)
        return response, 5


def _gateway(tmp_path: Path, provider: FakeProvider, mode="live") -> ModelGateway:
    routes = {tier: ModelRoute("test", f"{tier}-model", "https://unused.invalid") for tier in TIERS}
    settings = ModelSettings(routes=routes, mode=mode, cassette_dir=tmp_path,
                             max_tokens_per_call=2048, max_tokens_per_run=10000)
    return ModelGateway(settings, provider=provider)


def test_spec_parser_builds_six_journeys_stable_claim_ids_and_replays_cassette(tmp_path):
    async def scenario():
        response = _spec_response()
        provider = FakeProvider([response])
        parser_gateway = _gateway(tmp_path, provider, mode="record")
        parsed = await parse_spec(
            "Conduit lets users sign up, log in, create articles, comment, favorite, and update a profile.",
            context={"README.md": "Visitors can browse a paginated feed."},
            gateway=parser_gateway,
            run_id="parser-run",
        )
        assert len(parsed.journeys) >= 6
        names = " ".join(journey.journey.casefold() for journey in parsed.journeys)
        assert "sign up" in names and "log in" in names and "create an article" in names
        assert parsed.claims[0].id == claim_id(parsed.claims[0].statement)
        assert parsed.claims[0].id != "model-generated-id"
        assert len(parsed.claims) == 3
        assert parsed.claims[0].journey_ids == ["journey-01", "journey-02"]
        assert parsed.journeys[0].claim_ids == [parsed.claims[0].id]
        assert parsed.journeys[1].claim_ids == [parsed.claims[0].id]
        assert claim_id("  Favorite count changes once. ") == claim_id("favorite   count changes once.")
        assert provider.calls == 1
        assert "Visitors can browse a paginated feed." in provider.requests[0]["prompt"]

        replay_provider = FakeProvider([])
        replay = await parse_spec(
            "Conduit lets users sign up, log in, create articles, comment, favorite, and update a profile.",
            context={"README.md": "Visitors can browse a paginated feed."},
            gateway=_gateway(tmp_path, replay_provider, mode="replay"),
            run_id="parser-replay",
        )
        assert replay == parsed
        assert replay_provider.calls == 0

    asyncio.run(scenario())


def test_spec_parser_fails_closed_after_gateway_retry(tmp_path):
    async def scenario():
        provider = FakeProvider([{"not_a_spec": True}, {"still_not_a_spec": True}])
        with pytest.raises(MalformedModelResponse):
            await parse_spec("A product description.", gateway=_gateway(tmp_path, provider))
        assert provider.calls == 2

    asyncio.run(scenario())


def test_playbook_emits_over_forty_schema_valid_cases_from_catalog():
    spec = Spec.model_validate(json.loads((FIXTURES / "spec.json").read_text(encoding="utf-8")))
    elements = [ElementCatalogEntry.model_validate(item)
                for item in json.loads((FIXTURES / "element_catalog.json").read_text(encoding="utf-8"))]
    fixture_cases = generate(spec, elements)
    assert len(fixture_cases) >= 40
    elements.append(ElementCatalogEntry(
        id="sort-title", role="button", name="Title", state={"sort_control": True},
        semantic_locator='role=button[name="Title"]', visible=True, enabled=True, in_viewport=True,
    ))
    elements.append(ElementCatalogEntry(
        id="numeric-quantity", role="spinbutton", name="Quantity",
        state={"field_type": "number", "min_value": "0"},
        semantic_locator='role=spinbutton[name="Quantity"]', form_group="checkout",
        visible=True, enabled=True, in_viewport=True,
    ))
    generated = generate(spec, elements)
    assert len(generated) >= 40
    assert all(TestCase.model_validate(case.model_dump()) == case for case in generated)
    assert len({case.id for case in generated}) == len(generated)
    assert {step.locator for case in generated for step in case.steps if step.locator} <= {
        element.semantic_locator for element in elements
    }
    flow_actions = {
        "form-double-submit": {"assert_double_submit"},
        "form-back-mid-flow": {"fill", "assert_back_mid_flow"},
        "form-refresh-mid-flow": {"fill", "assert_refresh_mid_flow"},
        "form-keyboard-submit": {"fill", "press", "assert_keyboard_submit"},
        "form-mobile-viewport": {"set_viewport", "fill", "assert_mobile_layout"},
        "form-throttled-network": {"fill", "throttle_network", "click"},
        "form-offline-toggle": {"fill", "set_offline", "click"},
        "form-empty-required": {"fill", "assert_invalid"},
        "form-max-length": {"type_text", "assert_value_length"},
        "form-max-length-1024": {"type_text", "assert_value_length"},
        "form-max-length-10000": {"type_text", "assert_value_length"},
        "form-numeric-boundary": {"fill", "assert_numeric_boundary", "assert_no_new_console_errors"},
        "form-unicode": {"fill", "assert_input_value"},
        "form-rtl-text": {"fill", "assert_input_value"},
        "form-sql-payload": {"press", "assert_no_new_console_errors"},
        "form-xss-payload": {"press", "assert_no_unsafe_markup"},
        "security-logged-out-protected": {"goto", "assert_protected_route"},
        "security-idor": {"assert_idor_isolation"},
        "list-sort-stability": {"assert_sort_stability"},
        "security-reflected-xss": {"press", "assert_no_unsafe_markup"},
        "list-broken-links": {"assert_internal_links"},
        "list-broken-images": {"assert_no_broken_images"},
        "list-console-errors": {"assert_no_console_errors"},
        "list-zero-result-filter": {"fill", "press", "assert_empty_state"},
        "list-empty-state": {"fill", "press", "assert_empty_state"},
        "list-malformed-filter": {"fill", "press", "assert_no_new_console_errors"},
        "list-whitespace-filter": {"fill", "press", "assert_no_new_console_errors"},
        "list-long-item-name": {"assert_no_text_overflow"},
        "list-accessible-names": {"assert_named_control"},
    }
    for check_id, required_actions in flow_actions.items():
        matching = [case for case in generated if case.id.startswith(f"playbook-{check_id}-")]
        assert matching
        assert required_actions <= {step.action for step in matching[0].steps}
    required_dossier_checks = {
        "form-empty-required", "form-max-length", "form-max-length-1024", "form-max-length-10000",
        "form-unicode", "form-rtl-text", "form-negative-number", "form-zero-number",
        "form-decimal-integer", "form-xss-payload", "form-sql-payload", "form-double-submit",
        "form-back-mid-flow", "form-refresh-mid-flow", "form-keyboard-submit",
        "form-mobile-viewport", "form-throttled-network", "form-offline-toggle",
        "list-pagination-boundary", "list-sort-stability", "list-zero-result-filter",
        "list-malformed-filter", "list-long-item-name", "list-broken-links",
        "list-broken-images", "list-console-errors", "security-logged-out-protected",
        "security-idor", "security-reflected-xss",
    }
    assert required_dossier_checks <= {check.id for check in registered_checks()}
    docs = (ROOT / "docs" / "playbook.md").read_text(encoding="utf-8")
    assert all(f"`{check.id}`" in docs for check in registered_checks())


def test_playbook_limits_specialized_checks_to_compatible_control_metadata():
    checks = {check.id: check for check in registered_checks()}
    elements = [
        ElementCatalogEntry(id="required", role="textbox", name="Title", state={"required": True},
                            semantic_locator='role=textbox[name="Title"]', form_group="form",
                            visible=True, enabled=True, in_viewport=True),
        ElementCatalogEntry(id="email", role="textbox", name="Email", state={"field_type": "email"},
                            semantic_locator='role=textbox[name="Email"]', form_group="form",
                            visible=True, enabled=True, in_viewport=True),
        ElementCatalogEntry(id="password", role="textbox", name="Password", state={"field_type": "password"},
                            semantic_locator='role=textbox[name="Password"]', form_group="form",
                            visible=True, enabled=True, in_viewport=True),
        ElementCatalogEntry(id="quantity", role="spinbutton", name="Quantity",
                            state={"field_type": "number", "min_value": "0", "step_value": "1"},
                            semantic_locator='role=spinbutton[name="Quantity"]', form_group="form",
                            visible=True, enabled=True, in_viewport=True),
    ]
    assert [entry.id for entry in checks["form-empty-required"].targets(elements)] == ["required"]
    assert [entry.id for entry in checks["form-invalid-email"].targets(elements)] == ["email"]
    assert [entry.id for entry in checks["form-password-masking"].targets(elements)] == ["password"]
    assert all(entry.id == "quantity" for entry in checks["form-negative-number"].targets(elements))
    assert {step.action for step in checks["form-invalid-email"].build(elements, elements[1]).steps} == {
        "fill", "assert_invalid",
    }
    assert {step.action for step in checks["form-password-masking"].build(elements, elements[2]).steps} == {
        "fill", "assert_password_masked",
    }
    assert {step.action for step in checks["form-negative-zero"].build(elements, elements[3]).steps} == {
        "fill", "assert_numeric_value",
    }


def test_keyboard_submit_assertion_requires_a_mutation_request():
    class Session:
        cdp_session = None

        def __init__(self, requests):
            self.requests = requests

    async def scenario():
        with pytest.raises(AssertionError, match="did not submit"):
            await _run_step(None, Step(action="assert_keyboard_submit"),
                            session=Session([]), request_baseline=0)
        await _run_step(None, Step(action="assert_keyboard_submit"),
                        session=Session([{"method": "POST", "url": "/api/articles"}]),
                        request_baseline=0)

    asyncio.run(scenario())


class FakeBinderModel:
    def __init__(self, response):
        self.response = response
        self.calls = 0
        self.requests = []

    async def generate(self, **kwargs):
        self.calls += 1
        self.requests.append(kwargs)
        return self.response


class FailingBinderModel:
    async def generate(self, **kwargs):
        raise RuntimeError("model unavailable")


def test_binder_resolves_locatorless_abstract_step_with_action_constrained_candidates():
    async def scenario():
        elements = [
            ElementCatalogEntry(id="submit", role="button", name="Continue",
                                semantic_locator='role=button[name="Continue"]',
                                visible=True, enabled=True, in_viewport=True),
            ElementCatalogEntry(id="email", role="textbox", name="Email address",
                                semantic_locator='role=textbox[name="Email address"]',
                                visible=True, enabled=True, in_viewport=True),
        ]
        model = FakeBinderModel({"bindings": [{"step_index": 0, "element_id": "email"}]})
        case = TestCase(id="abstract-fill", journey="Register", description="Fill the email address",
                        steps=[Step(action="fill")])
        result = (await bind_cases([case], elements, gateway=model))[0]
        assert result.verdict == "BOUND"
        assert result.model_steps == [0]
        assert model.calls == 1
        assert result.test_case.steps[0].locator == elements[1].semantic_locator
        assert '"compatible_element_ids": ["email"]' in model.requests[0]["prompt"]

    asyncio.run(scenario())


def test_binder_preserves_global_keyboard_steps_without_model_calls():
    async def scenario():
        model = FakeBinderModel({})
        case = TestCase(id="keyboard-global", journey="Keyboard navigation",
                        description="Tab through the form",
                        steps=[Step(action="press", value="Tab")])
        result = (await bind_cases([case], [], gateway=model))[0]
        assert result.verdict == "BOUND"
        assert result.deterministic_steps == [0]
        assert result.test_case.steps[0].locator == ""
        assert model.calls == 0

    asyncio.run(scenario())


def test_binder_compatibility_keeps_numeric_fields_fillable_but_rejects_buttons():
    field = ElementCatalogEntry(id="quantity", role="spinbutton", name="Quantity",
                                semantic_locator='role=spinbutton[name="Quantity"]',
                                visible=True, enabled=True, in_viewport=True)
    button = ElementCatalogEntry(id="continue", role="button", name="Continue",
                                 semantic_locator='role=button[name="Continue"]',
                                 visible=True, enabled=True, in_viewport=True)
    step = Step(action="fill")
    assert _action_compatible(step, field)
    assert not _action_compatible(step, button)


def test_binder_uses_unique_deterministic_match_without_model_call():
    async def scenario():
        elements = [ElementCatalogEntry.model_validate(item)
                    for item in json.loads((FIXTURES / "element_catalog.json").read_text(encoding="utf-8"))]
        model = FakeBinderModel({})
        case = TestCase(id="case-1", journey="Favorite", description="Favorite article",
                        steps=[Step(action="click", locator="role=button[name=Favorite]")])
        result = (await bind_cases([case], elements, gateway=model))[0]
        assert result.verdict == "BOUND"
        assert result.deterministic_steps == [0]
        assert model.calls == 0
        assert result.test_case.steps[0].locator in {item.semantic_locator for item in elements}

    asyncio.run(scenario())


def test_binder_uses_high_confidence_deterministic_fallback_when_model_fails():
    async def scenario():
        elements = [ElementCatalogEntry(id="favorite", role="button", name="Favorite",
                                        semantic_locator='role=button[name="Favorite"]',
                                        visible=True, enabled=True, in_viewport=True)]
        case = TestCase(id="case-fallback", journey="Favorite", description="Favorite item",
                        steps=[Step(action="click", locator="role=button[name=Favorite item]")])
        result = (await bind_cases([case], elements, gateway=FailingBinderModel(),
                                   deterministic_threshold=1.0))[0]
        assert result.verdict == "BOUND"
        assert result.deterministic_steps == [0]
        assert result.model_steps == []
        assert result.test_case.steps[0].locator == elements[0].semantic_locator

    asyncio.run(scenario())


def test_binder_meets_ninety_percent_deterministic_fixture_coverage():
    async def scenario():
        elements = [ElementCatalogEntry.model_validate(item)
                    for item in json.loads((FIXTURES / "element_catalog.json").read_text(encoding="utf-8"))]
        cases = [TestCase.model_validate(item)
                 for item in json.loads((FIXTURES / "test_cases.json").read_text(encoding="utf-8"))]
        model = FakeBinderModel({})
        results = await bind_cases(cases, elements, gateway=model)
        interactive_steps = [step for case in cases for step in case.steps
                             if step.action in {"click", "double_click", "fill", "type_text", "hover", "press"}]
        deterministic_count = sum(len(result.deterministic_steps) for result in results)
        assert deterministic_count / len(interactive_steps) >= 0.9
        assert all(result.verdict == "BOUND" for result in results)
        assert model.calls == 0

    asyncio.run(scenario())


def test_binder_uses_one_catalog_constrained_call_for_ambiguous_match():
    async def scenario():
        elements = [
            ElementCatalogEntry(id="favorite-a", role="button", name="Favorite",
                                semantic_locator='role=button[name="Favorite"] >> nth=0',
                                visible=True, enabled=True, in_viewport=True),
            ElementCatalogEntry(id="favorite-b", role="button", name="Favorite",
                                semantic_locator='role=button[name="Favorite"] >> nth=1',
                                visible=True, enabled=True, in_viewport=True),
        ]
        model = FakeBinderModel({"bindings": [{"step_index": 0, "element_id": "favorite-b"}]})
        case = TestCase(id="case-2", journey="Favorite", description="Favorite the second article",
                        steps=[Step(action="click", locator="role=button[name=Favorite]", value="private test value")])
        result = (await bind_cases([case], elements, gateway=model))[0]
        assert result.verdict == "BOUND"
        assert result.model_steps == [0]
        assert model.calls == 1
        assert model.requests[0]["tier"] == "cheap"
        assert "private test value" not in model.requests[0]["prompt"]
        assert result.test_case.steps[0].locator == elements[1].semantic_locator
        assert "xpath" not in result.test_case.steps[0].locator.casefold()

    asyncio.run(scenario())


def test_binder_batches_ambiguous_steps_into_one_model_call_per_case():
    async def scenario():
        elements = [
            ElementCatalogEntry(id="favorite-a", role="button", name="Favorite",
                                semantic_locator='role=button[name="Favorite"] >> nth=0',
                                visible=True, enabled=True, in_viewport=True),
            ElementCatalogEntry(id="favorite-b", role="button", name="Favorite",
                                semantic_locator='role=button[name="Favorite"] >> nth=1',
                                visible=True, enabled=True, in_viewport=True),
        ]
        model = FakeBinderModel({"bindings": [
            {"step_index": 0, "element_id": "favorite-a"},
            {"step_index": 1, "element_id": "favorite-b"},
        ]})
        case = TestCase(id="case-batch", journey="Favorite", description="Favorite two items",
                        steps=[Step(action="click", locator="role=button[name=Favorite]"),
                               Step(action="click", locator="role=button[name=Favorite]")])
        result = (await bind_cases([case], elements, gateway=model))[0]
        assert result.verdict == "BOUND"
        assert model.calls == 1
        assert result.model_steps == [0, 1]
        assert [step.locator for step in result.test_case.steps] == [
            elements[0].semantic_locator, elements[1].semantic_locator,
        ]

    asyncio.run(scenario())


def test_binder_marks_unresolvable_target_inconclusive():
    async def scenario():
        elements = [ElementCatalogEntry(id="favorite", role="button", name="Favorite",
                                        semantic_locator='role=button[name="Favorite"]',
                                        visible=True, enabled=True, in_viewport=True)]
        model = FakeBinderModel({"bindings": []})
        case = TestCase(id="case-3", journey="Delete account", description="Target missing control",
                        steps=[Step(action="click", locator="role=button[name=Delete account]")])
        result = (await bind_cases([case], elements, gateway=model))[0]
        assert result.verdict == "INCONCLUSIVE"
        assert result.reason
        assert model.calls == 1

    asyncio.run(scenario())
