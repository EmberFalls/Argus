"""Canonical Argus Pydantic contracts shared by backend and generated clients."""

from .models import (
    AppGraph, BindingResult, BugReport, ConsoleEvent, CreateRunRequest, ElementCatalogEntry,
    Evidence, Finding, GateResult, ManifestBug, NetworkEvent, QAState,
    ReproductionResult, RunEvent, RunMetrics, RunSummary, Spec, SpecClaim,
    SpecEntity, Step, StepEvidence, TestCase, TestResult, ValidationRule, VerificationResult,
)

__all__ = [
    "AppGraph", "BindingResult", "BugReport", "ConsoleEvent", "ElementCatalogEntry", "Evidence",
    "CreateRunRequest", "Finding", "GateResult", "ManifestBug", "NetworkEvent",
    "QAState", "ReproductionResult", "RunEvent", "RunMetrics", "RunSummary",
    "Spec", "SpecClaim", "SpecEntity", "Step", "StepEvidence", "TestCase", "TestResult",
    "ValidationRule", "VerificationResult",
]
