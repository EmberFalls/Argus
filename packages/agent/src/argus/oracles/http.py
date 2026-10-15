from argus.state.evidence import Evidence


def check_http(evidence: Evidence) -> list[str]:
    return [f"HTTP {event.status} from {event.url}" for event in evidence.network
            if event.status is not None and event.status >= 500]
