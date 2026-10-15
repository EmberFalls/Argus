def deduplicate(reports: list[dict]) -> list[dict]:
    unique: dict[tuple[str, tuple[str, ...]], dict] = {}
    for report in reports:
        key = (report.get("title", "").casefold(), tuple(sorted(report.get("affected_paths", []))))
        unique.setdefault(key, report)
    return list(unique.values())
