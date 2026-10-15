"""Fixture-backed role implementations used for local vertical development."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

from argus_contracts.artifacts import RunArtifactLayout
from argus_contracts.models import (
    AppGraph, BindingResult, BugReport, ElementCatalogEntry, Evidence, Finding, GateResult,
    QAState, RunEvent, Spec, TestCase, TestResult, VerificationResult,
)

from argus.components import ComponentRegistry, DemoExplorer, DemoTester
from argus.models import ModelGateway
from argus.spec.binder import SemanticTestBinder
from argus.spec.parser import ModelSpecParser
from argus.spec.playbook import HeuristicPlaybookGenerator
from argus.reporter.playwright_export import export_test

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "fixtures"


class GoldenFixtures:
    """Load and validate the complete checked-in golden fixture set."""

    def __init__(self, root: Path = FIXTURE_DIR):
        self.root = root
        self.spec = Spec.model_validate(self._json("spec.json"))
        self.app_graph = AppGraph.model_validate(self._json("app_graph.json"))
        self.elements = [ElementCatalogEntry.model_validate(row) for row in self._json("element_catalog.json")]
        self.test_cases = [TestCase.model_validate(row) for row in self._json("test_cases.json")]
        self.test_results = [TestResult.model_validate(row) for row in self._json("test_results.json")]
        self.findings = [Finding.model_validate(row) for row in self._json("findings.json")]
        self.evidence = {
            path.stem: Evidence.model_validate(json.loads(path.read_text(encoding="utf-8")))
            for path in (root / "evidence").glob("*.json")
        }
        self.bug_reports = [BugReport.model_validate(row) for row in self._json("bug_reports.json")]
        self.gates = [GateResult.model_validate(row) for row in self._json("gate_results.json")]
        self.verifications = [VerificationResult.model_validate(row) for row in self._json("verification_results.json")]
        self.run_events = [RunEvent.model_validate_json(line) for line in (root / "run_events.ndjson").read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(self.run_events) < 50:
            raise ValueError("run_events.ndjson must contain a full-run trace (at least 50 events)")

    def _json(self, name: str):
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    def evidence_for(self, finding: Finding) -> Evidence:
        key = Path(finding.evidence_ref).stem
        return self.evidence[key]


class FixtureExplorer:
    def __init__(self, fixtures: GoldenFixtures): self.fixtures = fixtures
    def explore(self, target_url: str) -> tuple[AppGraph, list[ElementCatalogEntry]]:
        return self.fixtures.app_graph, self.fixtures.elements


class FixtureSpecParser:
    def __init__(self, fixtures: GoldenFixtures): self.fixtures = fixtures
    async def parse(self, description: str, context: dict[str, str] | None = None) -> Spec:
        return self.fixtures.spec.model_copy(update={"description": description or self.fixtures.spec.description})


class FixturePlaybookGenerator:
    def __init__(self, fixtures: GoldenFixtures): self.fixtures = fixtures
    def generate(self, spec: Spec, elements: Sequence[ElementCatalogEntry] | None = None) -> list[TestCase]:
        return [case for case in self.fixtures.test_cases if case.source == "playbook"]


class FixtureBinder:
    async def bind(self, test_cases: Sequence[TestCase], elements: Sequence[ElementCatalogEntry]) -> list[BindingResult]:
        available = {element.semantic_locator for element in elements}
        bound = []
        for case in test_cases:
            unresolved = []
            for step in case.steps:
                if step.action in {"click", "double_click", "fill", "type_text", "hover", "press"} and step.locator not in available:
                    unresolved.append(step.locator)
            bound.append(BindingResult(
                test_case=TestCase.model_validate(case.model_dump()),
                verdict="INCONCLUSIVE" if unresolved else "BOUND",
                reason=(f"No fixture element matches semantic locator(s): {', '.join(unresolved)}"
                        if unresolved else ""),
                deterministic_steps=[
                    index for index, step in enumerate(case.steps)
                    if step.action in {"click", "double_click", "fill", "type_text", "hover", "press"} and step.locator in available
                ],
            ))
        return bound


class FixtureTester:
    def __init__(self, fixtures: GoldenFixtures): self.fixtures = fixtures
    def run(self, test_cases: Sequence[TestCase], target_url: str) -> list[TestResult]:
        selected = {case.id for case in test_cases}
        return [result for result in self.fixtures.test_results if result.test_id in selected]


class FixtureOracle:
    def __init__(self, fixtures: GoldenFixtures): self.fixtures = fixtures
    def evaluate(self, result: TestResult) -> list[Finding]:
        mapping = {"tc-favorite-double": "finding-true", "tc-pagination-flaky": "finding-flaky",
                   "tc-analytics-noise": "finding-false-positive"}
        finding_id = mapping.get(result.test_id)
        return [finding for finding in self.fixtures.findings if finding.id == finding_id]


class FixtureGate:
    def __init__(self, fixtures: GoldenFixtures): self.results = {item.finding_id: item for item in fixtures.gates}
    def evaluate(self, finding: Finding, evidence: Evidence) -> GateResult:
        return self.results[finding.id]


class FixtureRedTeam:
    def __init__(self, fixtures: GoldenFixtures): self.results = {item.finding_id: item for item in fixtures.verifications}
    def verify(self, finding: Finding, spec: Spec, evidence: Evidence) -> VerificationResult:
        return self.results[finding.id]


class FixtureReporter:
    def build(self, findings: Sequence[Finding], gates: Sequence[GateResult],
              verifications: Sequence[VerificationResult],
              evidence_by_finding: dict[str, Evidence]) -> list[BugReport]:
        accepted = {item.finding_id for item in gates if item.verdict == "ACCEPTED"}
        confirmed = {item.finding_id for item in verifications if item.verdict == "CONFIRMED"}
        reports = []
        for finding in findings:
            if finding.id not in (accepted & confirmed):
                continue
            reports.append(BugReport(
                id=f"report-{finding.id}", severity="P1", title=finding.symptom_signature,
                category="functional", steps=finding.steps, expected=finding.expected,
                actual=finding.actual, evidence=evidence_by_finding[finding.id],
                playwright_repro_path=f"tests/repro/{finding.id}.spec.ts",
                affected_paths=finding.affected_paths, verified_by="red_team",
            ))
        return reports


class FixtureExporter:
    def export(self, test_cases: Sequence[TestCase], destination: Path) -> list[Path]:
        return [export_test(case, destination / f"{case.id}.spec.ts") for case in test_cases]


class FixtureEventBus:
    def __init__(self, layout: RunArtifactLayout): self.layout = layout
    def emit(self, event: RunEvent) -> None:
        # Revalidate at the event boundary before persisting the NDJSON record.
        self.layout.append_event(RunEvent.model_validate(event.model_dump()))


def build_demo_registry(fixtures: GoldenFixtures, layout: RunArtifactLayout) -> ComponentRegistry:
    """Create the default fixture roles and deterministic swap-in demo roles."""
    registry = ComponentRegistry()
    registry.register_fixture("explorer", lambda: FixtureExplorer(fixtures))
    registry.register_fixture("spec_parser", lambda: FixtureSpecParser(fixtures))
    registry.register_fixture("playbook", lambda: FixturePlaybookGenerator(fixtures))
    registry.register_fixture("binder", FixtureBinder)
    registry.register_fixture("tester", lambda: FixtureTester(fixtures))
    registry.register_fixture("oracle", lambda: FixtureOracle(fixtures))
    registry.register_fixture("gate", lambda: FixtureGate(fixtures))
    registry.register_fixture("red_team", lambda: FixtureRedTeam(fixtures))
    registry.register_fixture("reporter", FixtureReporter)
    registry.register_fixture("exporter", FixtureExporter)
    registry.register_fixture("event_bus", lambda: FixtureEventBus(layout))

    registry.register_real(
        "explorer", lambda: DemoExplorer(FixtureExplorer(fixtures))
    )
    registry.register_real("tester", lambda: DemoTester(FixtureTester(fixtures)))
    registry.register_real("spec_parser", lambda: ModelSpecParser(ModelGateway()))
    registry.register_real("playbook", HeuristicPlaybookGenerator)
    registry.register_real("binder", lambda: SemanticTestBinder(ModelGateway()))
    return registry


def run_stub_demo(
    output_dir: Path,
    *,
    real_roles: tuple[str, ...] = (),
    registry: ComponentRegistry | None = None,
    run_id: str | None = None,
) -> dict:
    """Run the sequential skeleton and persist its validated demo artifacts."""
    fixtures = GoldenFixtures()
    run_id = run_id or uuid4().hex
    layout = RunArtifactLayout(output_dir / "runs", run_id).initialize()
    registry = registry or build_demo_registry(fixtures, layout)
    roles = registry.build(real_roles)

    spec = asyncio.run(roles["spec_parser"].parse(fixtures.spec.description))
    app_graph, elements = roles["explorer"].explore("https://demo.realworld.io")
    test_cases = list(spec.journeys) + roles["playbook"].generate(spec, elements)
    binding_results = asyncio.run(roles["binder"].bind(test_cases, elements))
    bound_cases = [result.test_case for result in binding_results if result.verdict == "BOUND"]
    test_results = roles["tester"].run(bound_cases, "https://demo.realworld.io")
    test_results.extend(
        TestResult(
            test_id=result.test_case.id,
            verdict="INCONCLUSIVE",
            evidence=Evidence(
                steps=result.test_case.steps,
                expected=result.test_case.expected,
                actual=result.reason,
            ),
            duration_ms=0,
        )
        for result in binding_results if result.verdict == "INCONCLUSIVE"
    )
    findings = [finding for result in test_results for finding in roles["oracle"].evaluate(result)]
    evidence_by_finding = {finding.id: fixtures.evidence_for(finding) for finding in findings}
    gates = [roles["gate"].evaluate(finding, evidence_by_finding[finding.id]) for finding in findings]
    verifications = [roles["red_team"].verify(finding, spec, evidence_by_finding[finding.id]) for finding in findings]
    reports = roles["reporter"].build(findings, gates, verifications, evidence_by_finding)
    exports = roles["exporter"].export(test_cases, layout.tests_dir)

    for event in fixtures.run_events:
        roles["event_bus"].emit(event.model_copy(update={"run_id": run_id}))
    verified_ids = {item.finding_id for item in verifications if item.verdict == "CONFIRMED"}
    accepted_ids = {item.finding_id for item in gates if item.verdict == "ACCEPTED"}
    state = QAState(
        target_url="https://demo.realworld.io", spec=spec, app_graph=app_graph,
        discovered_elements=elements, test_cases=test_cases, test_results=test_results,
        findings=findings, accepted_findings=[f for f in findings if f.id in accepted_ids],
        verified_findings=[f for f in findings if f.id in verified_ids],
        rejected_findings=[f for f in findings if any(v.finding_id == f.id and v.verdict == "REFUTED" for v in verifications)],
        bugs_found=reports, coverage={"functional": 0.04},
        metrics={"fixture_events": len(fixtures.run_events), "exported_tests": len(exports)},
        iteration=1, complete=True,
    )
    layout.write_state(state.model_dump(mode="json", by_alias=True))
    (layout.reports_dir / "bug_reports.json").write_text(
        json.dumps([report.model_dump(mode="json", by_alias=True) for report in reports], indent=2) + "\n",
        encoding="utf-8",
    )
    return {"run_id": run_id, "artifact_dir": str(layout.run_dir), "state": state,
            "gates": gates, "verifications": verifications, "exports": exports,
            "event_count": len(fixtures.run_events), "real_roles": tuple(sorted(real_roles)),
            "reports": reports}
