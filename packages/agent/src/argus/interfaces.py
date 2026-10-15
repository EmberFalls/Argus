"""Stable role boundaries for independently developed Argus verticals.

Implementations may be live services or deterministic fixture-backed stubs. Each
method returns the corresponding F-01 Pydantic contract so callers can validate
boundaries without depending on a concrete implementation.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from argus_contracts.models import (
    AppGraph, BindingResult, BugReport, ElementCatalogEntry, Evidence, Finding, GateResult,
    RunEvent, Spec, TestCase, TestResult, VerificationResult,
)


@runtime_checkable
class Explorer(Protocol):
    def explore(self, target_url: str) -> tuple[AppGraph, list[ElementCatalogEntry]]: ...


@runtime_checkable
class SpecParser(Protocol):
    async def parse(self, description: str, context: dict[str, str] | None = None) -> Spec: ...


@runtime_checkable
class PlaybookGenerator(Protocol):
    def generate(
        self, spec: Spec, elements: Sequence[ElementCatalogEntry] | None = None
    ) -> list[TestCase]: ...


@runtime_checkable
class Binder(Protocol):
    async def bind(
        self, test_cases: Sequence[TestCase], elements: Sequence[ElementCatalogEntry]
    ) -> list[BindingResult]: ...


@runtime_checkable
class Tester(Protocol):
    def run(self, test_cases: Sequence[TestCase], target_url: str) -> list[TestResult]: ...


@runtime_checkable
class Oracle(Protocol):
    def evaluate(self, result: TestResult) -> list[Finding]: ...


@runtime_checkable
class Gate(Protocol):
    def evaluate(self, finding: Finding, evidence: Evidence) -> GateResult: ...


@runtime_checkable
class RedTeam(Protocol):
    def verify(self, finding: Finding, spec: Spec, evidence: Evidence) -> VerificationResult: ...


@runtime_checkable
class Reporter(Protocol):
    def build(
        self,
        findings: Sequence[Finding],
        gates: Sequence[GateResult],
        verifications: Sequence[VerificationResult],
        evidence_by_finding: dict[str, Evidence],
    ) -> list[BugReport]: ...


@runtime_checkable
class Exporter(Protocol):
    def export(self, test_cases: Sequence[TestCase], destination: Path) -> list[Path]: ...


@runtime_checkable
class EventBus(Protocol):
    def emit(self, event: RunEvent) -> None: ...
