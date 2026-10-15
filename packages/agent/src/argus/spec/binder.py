from collections.abc import Sequence

from argus_contracts.models import ElementCatalogEntry, TestCase


def bind(test_cases: Sequence[TestCase], elements: Sequence[ElementCatalogEntry]) -> list[TestCase]:
    """Validate existing semantic locator bindings against the Explorer catalog."""
    locators = {element.semantic_locator for element in elements}
    bound = []
    for case in test_cases:
        for step in case.steps:
            if step.action in {"click", "fill", "hover"} and step.locator not in locators:
                raise ValueError(f"No discovered element matches {step.locator!r}")
        bound.append(TestCase.model_validate(case.model_dump()))
    return bound
