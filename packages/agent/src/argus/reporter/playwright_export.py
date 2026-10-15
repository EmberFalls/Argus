from pathlib import Path

from argus.state.test_case import TestCase


def export_test(case: TestCase, destination: Path) -> Path:
    actions = []
    for step in case.steps:
        if step.action == "goto":
            actions.append(f"  await page.goto({(step.value or step.locator)!r});")
        elif step.action == "click":
            actions.append(f"  await page.getByRole('button', {{ name: {step.locator!r} }}).click();")
        elif step.action == "fill":
            actions.append(f"  await page.getByLabel({step.locator!r}).fill({(step.value or '')!r});")
        elif step.action == "assert":
            actions.append(f"  await expect(page.getByText({(step.value or step.locator)!r})).toBeVisible();")
        elif step.action == "wait":
            actions.append(f"  await page.waitForTimeout({min(step.timeout_ms, 10000)});")
        elif step.action == "hover":
            actions.append(f"  await page.getByRole('button', {{ name: {step.locator!r} }}).hover();")
    source = ("import { test, expect } from '@playwright/test';\n\n"
              f"test({case.description!r}, async ({{ page }}) => {{\n" + "\n".join(actions) + "\n});\n")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source, encoding="utf-8")
    return destination
