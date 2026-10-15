from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


async def replay_finding(replay: Callable[[], Awaitable[bool]], attempts: int = 3) -> dict:
    """Accept a finding only when its failure is reproduced in a majority of isolated replays."""
    successes = 0
    for _ in range(max(1, attempts)):
        try:
            successes += bool(await replay())
        except Exception as exc:  # noqa: BLE001 - a failed replay counts as a non-reproduction
            logger.warning("Finding replay attempt failed: %s", exc)
            continue
    return {"attempts": attempts, "successes": successes, "accepted": successes >= (attempts // 2 + 1)}
