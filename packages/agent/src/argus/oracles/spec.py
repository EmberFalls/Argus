def check_expected_text(expected: str, actual_text: str) -> list[str]:
    if expected and expected.casefold() not in actual_text.casefold():
        return [f"Expected text not found: {expected}"]
    return []
