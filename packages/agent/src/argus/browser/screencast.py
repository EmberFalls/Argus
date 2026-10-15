"""Chromium CDP screencast capture, kept outside the target page DOM."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from playwright.async_api import CDPSession
from playwright.async_api import Error as PlaywrightError


class CdpScreencastCapture:
    """Capture bounded 720p JPEG frames from one Chromium CDP session."""

    def __init__(
        self,
        session: CDPSession,
        publish: Callable[[dict[str, Any]], None],
        *,
        max_width: int = 1280,
        max_height: int = 720,
        quality: int = 65,
    ) -> None:
        self.session = session
        self.publish = publish
        self.max_width = max_width
        self.max_height = max_height
        self.quality = quality
        self._listener: Callable[[dict[str, Any]], None] | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self.session.send("Page.enable")

        def on_frame(frame: dict[str, Any]) -> None:
            self.publish({
                "data": frame.get("data", ""),
                "metadata": frame.get("metadata", {}),
            })
            session_id = frame.get("sessionId")
            if session_id is not None:
                try:
                    asyncio.get_running_loop().create_task(
                        self.session.send("Page.screencastFrameAck", {"sessionId": session_id})
                    )
                except RuntimeError:
                    pass

        self._listener = on_frame
        self.session.on("Page.screencastFrame", on_frame)
        await self.session.send(
            "Page.startScreencast",
            {
                "format": "jpeg",
                "quality": self.quality,
                "maxWidth": self.max_width,
                "maxHeight": self.max_height,
                "everyNthFrame": 1,
            },
        )
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        if self._listener is not None:
            self.session.remove_listener("Page.screencastFrame", self._listener)
            self._listener = None
        try:
            await self.session.send("Page.stopScreencast")
        except PlaywrightError:
            # The browser may already have closed the target while shutting down.
            pass
