"""
Slack job scheduler — thin alias over FastAPIJobScheduler.

The Slack adapter runs inside the same FastAPI process, so we reuse the
asyncio-based scheduler already used by the FastAPI platform.
"""

from platforms.fastapi.scheduler import FastAPIJobScheduler


class SlackJobScheduler(FastAPIJobScheduler):
    """Job scheduler for the Slack platform (asyncio-based)."""
