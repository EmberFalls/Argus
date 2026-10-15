from __future__ import annotations

from collections.abc import Awaitable, Callable


async def replay_finding(replay: Callable[[], Awaitable[bool]], attempts: int = 3) -> dict:
    """Accept a finding only when its failure is reproduced in a majority of isolated replays."""
    successes = 0
    for _ in range(max(1, attempts)):
        try:
            successes += bool(await replay())
        except Exception:
            continue
    return {"attempts": attempts, "successes": successes, "accepted": successes >= (attempts // 2 + 1)}
