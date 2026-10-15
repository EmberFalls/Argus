from argus_contracts.models import Spec, TestCase

PLAYBOOK = {
    "forms": ["empty submission", "invalid input", "double submission"],
    "navigation": ["direct route load", "back and forward navigation"],
    "state": ["reload after update", "repeated action"],
}


def generate(spec: Spec) -> list[TestCase]:
    """Turn the deterministic bug-bash catalog into typed edge-case cases."""
    return [
        TestCase(id=f"playbook-{category}-{index:02d}", journey=category.title(),
                 description=description, steps=[], expected="The application handles this case safely.",
                 category="edge_case", source="playbook")
        for category, descriptions in PLAYBOOK.items()
        for index, description in enumerate(descriptions, 1)
    ]
