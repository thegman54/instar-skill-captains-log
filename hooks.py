"""
What this skill offers, and what it is doing right now.

The surface asks (project-instar fires SkillHooks.on_capabilities); this answers in
MEANING ONLY. There is deliberately no colour, no layout, no animation and no UI word
anywhere in this file: a skill that learns what a tile is becomes impossible to render
anywhere else, and this same declaration has to serve a chat page, a terminal and a
voice-only client equally.

The live half is the whole point. This skill already knows whether a log is open and how
much is in it. Without this hook, saying so is the BOT's job to remember — and
remembering to mention state in the one turn where it matters is exactly what a
next-token model does not reliably do.

Cheap and side-effect free. It is called to draw a screen, not to do work: one indexed
lookup for the open log, nothing written, and `sweep()` is deliberately NOT called here
because expiring rows is work and this is a question.
"""

import structlog

from ..base import SkillHooks
from ._log import get_open_log
from ._speaker import resolve_speaker

log = structlog.get_logger()


# MUST be named exactly `Hooks` — the loader looks up that attribute by name and
# returns silently if it is missing, so a well-written file under any other name is
# simply never called.
class Hooks(SkillHooks):

    # (ctx, payload) — /hooks/<event> always passes a payload positionally, so a
    # one-argument signature raises TypeError and the hook silently returns nothing.
    async def on_capabilities(self, ctx: dict, payload: dict = None):
        from ...db import get_pool

        pool = get_pool()
        if not pool:
            # No database means the skill cannot act, which is a real state and worth
            # saying rather than silently offering functions that would fail.
            return {"capabilities": [
                {"id": "captains_log", "title": "Captain's Log",
                 "summary": "Unavailable — no database configured", "state": "error"},
            ]}

        open_log = None
        try:
            who = await resolve_speaker(self)
            async with pool.acquire() as conn:
                open_log = await get_open_log(conn, who["speaker_id"], who["session_id"])
        except Exception as e:                                   # noqa: BLE001
            # A capability list is drawn on screen; failing to build one must degrade to
            # "here is what exists" rather than taking the screen down with it.
            log.warning("captains_log_capabilities_failed", error=str(e))

        if open_log:
            n = open_log["entry_count"]
            return {"capabilities": [
                {"id": "captains_log_append", "title": "Recording",
                 "summary": "Capturing this conversation — " +
                            (str(n) + " entries so far" if n else "nothing captured yet"),
                 "state": "running"},
                {"id": "captains_log_end", "title": "Close",
                 "summary": "Compile the log into a document for approval",
                 "state": "available"},
                {"id": "captains_log_status", "title": "Status",
                 "summary": "What is in the log so far", "state": "available"},
                # Begin is not offered while one is open: a second log cannot be started,
                # so showing it as available would be a lie the page would faithfully draw.
                {"id": "captains_log_begin", "title": "Start",
                 "summary": "A log is already open", "state": "disabled"},
            ]}

        return {"capabilities": [
            {"id": "captains_log_begin", "title": "Start",
             "summary": "Open a new log and record this conversation",
             "state": "available"},
            {"id": "captains_log_read", "title": "Read",
             "summary": "Open a previous log", "state": "available"},
            {"id": "captains_log_search", "title": "Search",
             "summary": "Find a log by topic, tag or date", "state": "available"},
            # Honest about what cannot be done yet, instead of omitting it: a function
            # that silently is not there reads as the skill being broken.
            {"id": "captains_log_end", "title": "Close",
             "summary": "No log is open", "state": "disabled"},
        ]}
