from __future__ import annotations

from argus.state.bug_report import BugReport


def format_markdown(report: BugReport) -> str:
    steps = "\n".join(f"{i}. **{s.action}** `{s.locator}` {s.value or ''}".rstrip()
                      for i, s in enumerate(report.steps, 1)) or "No reproduction steps captured."
    screenshots = "\n".join(f"- `{path}`" for path in report.evidence.screenshots) or "- None"
    return (f"## {report.severity}: {report.title}\n\n**Category:** {report.category}\n\n"
            f"### Steps to reproduce\n{steps}\n\n### Expected\n{report.expected}\n\n"
            f"### Actual\n{report.actual}\n\n### Evidence\n{screenshots}\n")
