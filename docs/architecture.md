# Architecture

Argus separates browser observations, deterministic execution, decision rules, and report generation. The browser is treated as an untrusted target: target page text is evidence, never agent instructions.

## Stage 2 request flow

1. CLI/API validates URL and run inputs.
2. Explorer captures the accessibility snapshot and semantic controls.
3. Tester executes explicit journey steps in an isolated browser context while collecting console, HTTP, DOM, and screenshot evidence.
4. Oracles flag deterministic failures; the Evidence Gate can replay a finding and only accepts reproducible results.
5. Reporter emits a structured report and exports passing journeys as Playwright tests.

Each state field has a single writer through `supervisor/state_writer.py`. The initial supervisor runs these steps sequentially. Parallel dispatch and model-backed Explorer/Red Team are planned interfaces, not currently claimed functionality.

## Packages

`packages/agent` owns runtime behavior. `packages/shared/schemas` publishes JSON Schema for consumers. `packages/ui` is a lightweight dashboard shell that can consume the API. Sample apps and the benchmark harness are kept outside the runtime package so benchmark truth can be managed independently.

## Trust boundaries

The target application and its DOM are untrusted. Actions are bounded by a supplied test journey; no arbitrary page-provided instruction is executed. Domain allowlists are configurable. Never point the runner at production workflows that can delete, purchase, or send real data.
