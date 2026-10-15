import json
import re
from pathlib import Path

from argus.state.test_case import TestCase


def _locator(locator: str) -> str:
    match = re.fullmatch(r"role=([\w-]+)(?:\[name=(.+)\])?(?: >> nth=(\d+))?", locator.strip())
    if not match:
        return f"page.getByText({json.dumps(locator, ensure_ascii=False)})"
    role, name, ordinal = match.groups()
    expression = f"page.getByRole({json.dumps(role)}, {{ name: {json.dumps(json.loads(name) if name and name.startswith(chr(34)) else name or '', ensure_ascii=False)} }})"
    return f"{expression}.nth({ordinal})" if ordinal is not None else expression


def export_test(case: TestCase, destination: Path, *, base_url: str | None = None) -> Path:
    actions = []
    if base_url:
        actions.append(
            "  await page.goto(process.env.ARGUS_BASE_URL ?? "
            f"{json.dumps(base_url, ensure_ascii=False)});"
        )
    for step in case.steps:
        if step.action == "goto":
            actions.append(f"  await page.goto(new URL({json.dumps(step.value or step.locator, ensure_ascii=False)}, page.url()).toString());")
        elif step.action == "click":
            actions.append(f"  await {_locator(step.locator)}.click();")
        elif step.action == "double_click":
            actions.append(f"  await {_locator(step.locator)}.dblclick();")
        elif step.action == "assert_double_submit":
            field = _locator(step.locator)
            actions.extend([
                "  var mutationBaseline = mutationRequests.length;",
                f"  await {field}.dblclick();",
                "  await page.waitForLoadState('networkidle', { timeout: 2000 }).catch(() => page.waitForTimeout(250));",
                "  const submittedMutations = mutationRequests.slice(mutationBaseline).map(item => `${item.method} ${item.url}`); if (!submittedMutations.length) test.skip(true, 'No mutation request observed'); const mutationCounts = new Map(); for (const mutation of submittedMutations) mutationCounts.set(mutation, (mutationCounts.get(mutation) || 0) + 1); expect([...mutationCounts.values()].every(count => count === 1)).toBe(true);",
            ])
        elif step.action == "fill":
            actions.append(f"  await {_locator(step.locator)}.fill({json.dumps(step.value or '', ensure_ascii=False)});")
        elif step.action == "type_text":
            actions.append(f"  await {_locator(step.locator)}.pressSequentially({json.dumps(step.value or '', ensure_ascii=False)});")
        elif step.action == "assert":
            actions.append(f"  await expect(page.getByText({json.dumps(step.value or step.locator, ensure_ascii=False)})).toBeVisible();")
        elif step.action == "wait":
            actions.append(f"  await page.waitForTimeout({min(step.timeout_ms, 10000)});")
        elif step.action == "hover":
            actions.append(f"  await {_locator(step.locator)}.hover();")
        elif step.action == "press":
            if step.locator:
                actions.append(f"  await {_locator(step.locator)}.press({json.dumps(step.value or 'Enter', ensure_ascii=False)});")
            else:
                actions.append(f"  await page.keyboard.press({json.dumps(step.value or 'Enter', ensure_ascii=False)});")
        elif step.action == "back":
            actions.append("  await page.goBack();")
        elif step.action == "reload":
            actions.append("  await page.reload();")
        elif step.action == "set_viewport":
            try:
                width, height = (int(value) for value in (step.value or "").split("x", 1))
                actions.append(f"  await page.setViewportSize({{ width: {width}, height: {height} }});")
            except (TypeError, ValueError):
                actions.append("  throw new Error('Invalid set_viewport step value');")
        elif step.action == "set_offline":
            actions.append(f"  await page.context().setOffline({(step.value or '').lower() == 'true'});")
        elif step.action == "throttle_network" and (step.value or "").lower() == "3g":
            actions.extend([
                "  const cdp = await page.context().newCDPSession(page);",
                "  await cdp.send('Network.enable');",
                "  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 400, downloadThroughput: 750 * 1024 / 8, uploadThroughput: 250 * 1024 / 8, connectionType: 'cellular3g' });",
            ])
        elif step.action == "assert_no_broken_images":
            actions.append("  const images = await page.locator('img').count(); if (!images) test.skip(true, 'No images to check');")
            actions.append("  expect(await page.locator('img').evaluateAll(images => images.filter(image => image.currentSrc && image.complete && image.naturalWidth === 0).map(image => image.currentSrc))).toEqual([]);")
        elif step.action == "assert_internal_links":
            actions.extend([
                "  const internalLinks = await page.locator('a[href]').evaluateAll(links => [...new Set(links.map(link => link.href).filter(href => { try { return new URL(href).origin === location.origin; } catch { return false; } }))]);",
                "  if (!internalLinks.length) test.skip(true, 'No same-origin links to check');",
                "  for (const href of internalLinks.slice(0, 50)) expect((await page.context().request.get(href)).status()).toBeLessThan(400);",
            ])
        elif step.action == "assert_no_console_errors":
            actions.append("  expect(consoleErrors).toEqual([]);")
        elif step.action == "assert_invalid":
            actions.append(f"  expect(await {_locator(step.locator)}.evaluate(element => element.getAttribute('aria-invalid') === 'true' || !element.checkValidity())).toBe(true);")
        elif step.action == "assert_password_masked":
            field = _locator(step.locator)
            actions.append(f"  expect(await {field}.getAttribute('type')).toBe('password');")
            actions.append(f"  expect(await page.locator('body').innerText()).not.toContain(await {field}.inputValue());")
        elif step.action == "assert_value_length":
            field = _locator(step.locator)
            try:
                expected_length = int(step.value or "")
                actions.append(f"  expect((await {field}.inputValue()).length).toBe({expected_length});")
            except ValueError:
                actions.append("  throw new Error('Invalid assert_value_length step value');")
        elif step.action == "assert_numeric_value":
            field = _locator(step.locator)
            try:
                expected_number = float(step.value or "")
                actions.append(f"  expect(Number(await {field}.inputValue())).toBe({expected_number});")
            except ValueError:
                actions.append("  throw new Error('Invalid assert_numeric_value step value');")
        elif step.action == "assert_numeric_boundary":
            field = _locator(step.locator)
            actions.append(f"  expect(await {field}.evaluate(element => element.type === 'number' && !element.validity.badInput && (!element.value || Number.isFinite(element.valueAsNumber)) && (!(element.validity.rangeOverflow || element.validity.rangeUnderflow) || !element.checkValidity()))).toBe(true);")
        elif step.action == "assert_mobile_layout":
            field = _locator(step.locator)
            actions.append(f"  expect(await {field}.evaluate(element => {{ const rect = element.getBoundingClientRect(); return !!element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden' && rect.left >= -1 && rect.right <= innerWidth + 1 && document.documentElement.scrollWidth <= innerWidth + 1; }})).toBe(true);")
        elif step.action == "assert_back_mid_flow":
            field = _locator(step.locator)
            actions.extend([
                "  const formUrlBeforeBack = page.url(); if (await page.evaluate(() => history.length) < 3) test.skip(true, 'No previous in-app history entry');",
                "  await page.goBack(); if (page.url() === formUrlBeforeBack || page.url() === 'about:blank') test.skip(true, 'Back did not reach an in-app page'); await page.goForward(); expect(page.url()).toBe(formUrlBeforeBack);",
                f"  expect(await {field}.inputValue()).toBe({json.dumps(step.value or '', ensure_ascii=False)});",
            ])
        elif step.action == "assert_refresh_mid_flow":
            actions.extend([
                "  const priorMutation = mutationRequests.filter(item => ['POST','PUT','PATCH','DELETE'].includes(item.method)).at(-1); if (!priorMutation) test.skip(true, 'No mutation request observed before refresh');",
                "  const mutationKey = `${priorMutation.method} ${priorMutation.url}`; const priorCount = mutationRequests.filter(item => `${item.method} ${item.url}` === mutationKey).length; await page.reload(); await page.waitForLoadState('networkidle', { timeout: 2000 }).catch(() => {}); expect(mutationRequests.filter(item => `${item.method} ${item.url}` === mutationKey).length).toBe(priorCount);",
            ])
        elif step.action == "assert_input_value":
            actions.append(f"  expect(await {_locator(step.locator)}.inputValue()).toBe({json.dumps(step.value or '', ensure_ascii=False)});")
        elif step.action == "assert_no_new_console_errors":
            actions.append("  expect(consoleErrors).toEqual([]);")
        elif step.action == "assert_no_unsafe_markup":
            actions.append("  expect(await page.evaluate(() => [...document.scripts].some(node => /alert\\s*\\(\\s*1\\s*\\)/i.test(node.textContent || '')) || [...document.images].some(node => node.getAttribute('src') === 'x' && /alert\\s*\\(\\s*1\\s*\\)/i.test(node.getAttribute('onerror') || '')))).toBe(false);")
        elif step.action == "assert_empty_state":
            actions.append("  await expect(page.locator('body')).toContainText(/no results|no matches|nothing found|no articles|no items/i);")
        elif step.action == "assert_no_text_overflow":
            actions.extend([
                "  const listNodes = page.locator('li, [role=listitem], tr, td, th, a');",
                "  const longItems = await listNodes.evaluateAll(nodes => nodes.filter(node => node.getClientRects().length && (node.innerText || node.textContent || '').trim().length >= 80));",
                "  if (!longItems.length) test.skip(true, 'No long list items to check');",
                "  expect(await listNodes.evaluateAll(nodes => nodes.filter(node => node.getClientRects().length && (node.innerText || node.textContent || '').trim().length >= 80 && node.scrollWidth > node.clientWidth + 1).map(node => node.innerText))).toEqual([]);",
            ])
        elif step.action == "assert_named_control":
            actions.append("  expect(await page.locator('a, button, input:not([type=hidden]), textarea, select, [role=button], [role=link]').evaluateAll(nodes => nodes.filter(node => node.getClientRects().length && !((node.getAttribute('aria-label') || '').trim() || (node.labels && [...node.labels].map(label => label.innerText.trim()).filter(Boolean).join(' ')) || (node.getAttribute('aria-labelledby') || '').split(/\\s+/).map(id => document.getElementById(id)?.innerText.trim() || '').filter(Boolean).join(' ') || (node.innerText || node.textContent || '').trim() || (['button','submit','reset','image'].includes((node.type || '').toLowerCase()) ? (node.value || '').trim() : '') || (node.getAttribute('alt') || '').trim() || (node.getAttribute('placeholder') || '').trim() || (node.getAttribute('title') || '').trim())))).toEqual([]);")
        elif step.action == "assert_pagination_boundaries":
            actions.extend([
                "  let firstPage = page.getByRole('button', { name: /\\b(first|first page)\\b/i }); if (!(await firstPage.count())) firstPage = page.getByRole('link', { name: /\\b(first|first page)\\b/i }); firstPage = firstPage.first();",
                "  let lastPage = page.getByRole('button', { name: /\\b(last|last page)\\b/i }); if (!(await lastPage.count())) lastPage = page.getByRole('link', { name: /\\b(last|last page)\\b/i }); lastPage = lastPage.first();",
                "  await firstPage.click();",
                "  let previous = page.getByRole('button', { name: /\\b(previous|prev)\\b/i }); if (!(await previous.count())) previous = page.getByRole('link', { name: /\\b(previous|prev)\\b/i }); previous = previous.first();",
                "  expect(await previous.evaluate(element => element.disabled || element.getAttribute('aria-disabled') === 'true')).toBe(true);",
                "  await lastPage.click();",
                "  let nextPage = page.getByRole('button', { name: /\\b(next|following)\\b/i }); if (!(await nextPage.count())) nextPage = page.getByRole('link', { name: /\\b(next|following)\\b/i }); nextPage = nextPage.first();",
                "  expect(await nextPage.evaluate(element => element.disabled || element.getAttribute('aria-disabled') === 'true')).toBe(true);",
            ])
        elif step.action == "assert_protected_route":
            actions.append("  const route = new URL(page.url()); const body = (await page.locator('body').innerText()).toLowerCase(); expect(/\\/(account|dashboard|settings|profile)(?:\\/|$)/i.test(route.pathname) && !/(sign in|log in|login|unauthorized|forbidden|access denied)/i.test(body)).toBe(false);")
        elif step.action == "assert_idor_isolation":
            actions.append("  test.skip(true, 'IDOR requires a configured two-user ownership fixture');")
        elif step.action == "assert_sort_stability":
            actions.extend([
                f"  const sortControl = {_locator(step.locator)};",
                "  const readSortedRows = () => sortControl.evaluate(control => { const header = control.closest('th, [role=columnheader]'); const table = header && header.closest('table, [role=table], [role=grid]'); if (!header || !table) return null; const headers = [...table.querySelectorAll('thead th, [role=columnheader]')]; const column = headers.indexOf(header); const rows = [...table.querySelectorAll('tbody tr, [role=row]')].filter(row => !row.querySelector('[role=columnheader]')); if (column < 0 || rows.length < 2) return null; return { direction: header.getAttribute('aria-sort') || '', rows: rows.map(row => { const cells = [...row.querySelectorAll('th, td, [role=gridcell], [role=rowheader]')]; return { key: (cells[column]?.innerText || '').trim(), identity: cells.map(cell => (cell.innerText || '').trim()).join(' | ') }; }) }; });",
                "  await sortControl.click(); const firstSort = await readSortedRows(); if (!firstSort) test.skip(true, 'No sortable table rows'); const duplicateKeys = new Set(firstSort.rows.filter(row => firstSort.rows.filter(other => other.key === row.key).length > 1).map(row => row.key)); if (!duplicateKeys.size) test.skip(true, 'No duplicate sort keys to assess stability'); await sortControl.click(); await sortControl.click(); const thirdSort = await readSortedRows(); if (!thirdSort) test.skip(true, 'Table changed shape during sorting'); if (firstSort.direction && thirdSort.direction && firstSort.direction !== thirdSort.direction) test.skip(true, 'Sort did not return to initial direction'); expect(thirdSort.rows.filter(row => duplicateKeys.has(row.key)).map(row => row.identity)).toEqual(firstSort.rows.filter(row => duplicateKeys.has(row.key)).map(row => row.identity));",
            ])
    console_setup = (
        "  const consoleErrors = [];\n"
        "  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });\n"
        "  page.on('pageerror', error => consoleErrors.push(error.message));\n"
        "  page.on('dialog', dialog => { consoleErrors.push(`JavaScript dialog: ${dialog.type()}`); void dialog.dismiss(); });\n"
        if any(step.action in {"assert_no_console_errors", "assert_no_new_console_errors", "assert_refresh_mid_flow"} for step in case.steps) else ""
    )
    mutation_setup = (
        "  const mutationRequests = [];\n"
        "  page.on('request', request => { if (['POST','PUT','PATCH','DELETE'].includes(request.method().toUpperCase())) mutationRequests.push({ method: request.method().toUpperCase(), url: request.url() }); });\n"
        if any(step.action in {"assert_refresh_mid_flow", "assert_double_submit"} for step in case.steps) else ""
    )
    metadata = [f"// Argus case: {json.dumps(case.id, ensure_ascii=False)}"]
    if case.claim_ids:
        metadata.append(f"// Spec claim IDs: {json.dumps(case.claim_ids, ensure_ascii=False)}")
    if case.expected:
        metadata.append(f"// Expected behavior: {json.dumps(case.expected, ensure_ascii=False)}")
    source = ("import { test, expect } from '@playwright/test';\n\n"
              + "\n".join(metadata) + "\n"
              + f"test({json.dumps(case.description, ensure_ascii=False)}, async ({{ page }}) => {{\n" + console_setup + mutation_setup + "\n".join(actions) + "\n});\n")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source, encoding="utf-8")
    return destination
