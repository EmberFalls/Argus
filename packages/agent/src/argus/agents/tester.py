from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import Evidence, RunEvent
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from argus.browser.session import BrowserSession
from argus.evidence.recorder import EvidenceRecorder
from argus.perception.a11y import resolve_semantic_locator
from argus.state.test_case import Step, TestCase


async def execute_case(session: BrowserSession, case: TestCase, layout: RunArtifactLayout,
                       *, initial_url: str | None = None,
                       synthetic_values: tuple[str, ...] = (),
                       on_action: Callable[[dict[str, Any]], None] | None = None) -> tuple[str, Evidence, int]:
    started = asyncio.get_running_loop().time()
    page = session.page
    recorder = EvidenceRecorder(session, layout, case.id, case.steps,
                                expected=case.expected, synthetic_values=synthetic_values)
    actual = "Journey completed."
    verdict = "PASS"
    if initial_url:
        recorder.current_step_index = 0
        try:
            await page.goto(initial_url, wait_until="domcontentloaded", timeout=30000)
        except PlaywrightError as exc:
            verdict, actual = "FAIL", f"{type(exc).__name__}: {exc}"
    for step_index, step in enumerate(case.steps):
        if verdict == "FAIL":
            break
        action = await _action_payload(page, step, step_index, case)
        layout.append_event(RunEvent(
            id=uuid4().hex,
            run_id=layout.run_dir.name,
            agent="tester",
            correlation_id=case.id,
            type="action",
            payload=action,
        ))
        if on_action is not None:
            on_action(action)
        await recorder.begin_step(
            step_index, _step_element(page, step),
            step=step,
            sensitive=bool(step.value and step.value in recorder.redactor.secret_values),
        )
        try:
            await _run_step(page, step)
        except PlaywrightError as exc:
            verdict, actual = "FAIL", f"{type(exc).__name__}: {exc}"
        await recorder.finish_step(step_index)
        if verdict == "FAIL":
            break
    evidence = await recorder.finish(actual=actual)
    elapsed = int((asyncio.get_running_loop().time() - started) * 1000)
    return verdict, evidence, elapsed


async def _action_payload(page: Page, step: Step, step_index: int, case: TestCase) -> dict[str, Any]:
    locator = step.locator or "target element"
    rationale = {
        "goto": "Open the page required for this journey.",
        "click": f"Activate {locator} to continue the {case.journey} journey.",
        "fill": f"Enter test data into {locator} for the {case.journey} journey.",
        "hover": f"Inspect the controls revealed by {locator}.",
        "wait": "Allow the page to settle before continuing.",
        "assert": f"Check the expected result: {locator}.",
    }[step.action]
    payload: dict[str, Any] = {
        "action": step.action,
        "locator": step.locator,
        "step_index": step_index,
        "rationale": rationale,
    }
    element = _step_element(page, step)
    if element is not None:
        try:
            box = await element.first.bounding_box()
            viewport = await page.evaluate("() => ({width: innerWidth, height: innerHeight})")
            if box is not None:
                payload.update({
                    "x": box["x"] + box["width"] / 2,
                    "y": box["y"] + box["height"] / 2,
                    "width": box["width"],
                    "height": box["height"],
                    "viewport_width": viewport["width"],
                    "viewport_height": viewport["height"],
                })
        except PlaywrightError:
            # The action still runs and reports its own locator error; an overlay is optional.
            pass
    return payload


def _step_element(page: Page, step: Step):
    if step.action in {"click", "fill", "hover"} and step.locator:
        return _semantic_locator(page, step.locator)
    if step.action == "assert":
        return page.get_by_text(step.value or step.locator, exact=False)
    return None


async def _run_step(page: Page, step: Step) -> None:
    if step.action == "goto":
        await page.goto(step.value or step.locator, wait_until="domcontentloaded", timeout=step.timeout_ms)
    elif step.action == "wait":
        await page.wait_for_timeout(min(step.timeout_ms, 10000))
    elif step.action == "assert":
        locator = page.get_by_text(step.value or step.locator, exact=False)
        await locator.first.wait_for(state="visible", timeout=step.timeout_ms)
    else:
        locator = _semantic_locator(page, step.locator)
        if step.action == "click":
            await locator.click(timeout=step.timeout_ms)
        elif step.action == "fill":
            await locator.fill(step.value or "", timeout=step.timeout_ms)
        elif step.action == "hover":
            await locator.hover(timeout=step.timeout_ms)


def _semantic_locator(page: Page, expression: str):
    """Resolve catalog semantic locators, including duplicate-name ordinals."""
    return resolve_semantic_locator(page, expression)
