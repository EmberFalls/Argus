from argus.state.evidence import Evidence


def check_console(evidence: Evidence) -> list[str]:
    return [event.message for event in evidence.console if event.level == "error"]
