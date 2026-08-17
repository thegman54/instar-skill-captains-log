"""
captains_log_end — close the open log, compile it, and hand it to the owner for approval.

Compilation happens here, once: the fragments are grouped by kind into a document (JSON +
markdown) and stored on the log. Nothing about the log is permanent until the owner
approves it in the admin panel — and if they don't, it expires.
"""

import structlog

from ..base import BaseTool, ToolResult
from ..registry import register_tool
from ._speaker import resolve_speaker
from ._log import PENDING_TTL_HOURS, close_log, get_open_log

log = structlog.get_logger()


@register_tool
class CaptainsLogEndTool(BaseTool):
    """Close and compile the open captain's log (owner approval required to keep it)."""

    @property
    def name(self) -> str:
        return "captains_log_end"

    @property
    def short_description(self) -> str:
        return "End and compile the open log"

    @property
    def description(self) -> str:
        return (
            "Close the OPEN captain's log and compile it into a document. Call this when the owner "
            "says 'end captain's log', 'close the log', or the conversation the log was opened for "
            "is plainly finished. "
            "Before calling, append anything that was established but not yet logged — this is the "
            "last chance; nothing is added after the log closes. "
            "Supply a `closing` summary: what this conversation amounted to, in a few sentences. "
            "The compiled log is a PROPOSAL — tell the owner it is waiting on their approval and "
            f"that it expires in {PENDING_TTL_HOURS} hours if they don't approve it."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "closing": {
                    "type": "string",
                    "description": "Closing summary — what the conversation amounted to, and where it leaves things. A few sentences.",
                },
                "add_tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to add to the log now that you know what it turned out to be about.",
                },
            },
            "required": ["closing"],
        }

    def credential_keys(self) -> list[str]:
        return []

    async def execute(self, closing: str, add_tags: list[str] = None, **kwargs) -> ToolResult:
        from ...db import get_pool

        pool = get_pool()
        if not pool:
            return ToolResult.fail("Database not available — the captains_log skill requires database configuration")

        who = await resolve_speaker(self)
        add_tags = [t.strip().lower() for t in (add_tags or []) if t and t.strip()]

        async with pool.acquire() as conn:
            open_log = await get_open_log(conn, who["speaker_id"], who["session_id"])
            if not open_log:
                return ToolResult.fail("No captain's log is open, so there is nothing to close.")

            if add_tags:
                await conn.execute(
                    """UPDATE captains_logs
                       SET tags = ARRAY(SELECT DISTINCT unnest(tags || $2::text[]))
                       WHERE id = $1""",
                    open_log["id"], add_tags,
                )

            result = await close_log(conn, open_log["id"], closing=closing.strip(), status="pending")

        if not result.get("entry_count"):
            log.info("captains_log_end_empty", id=str(open_log["id"]))
            return ToolResult.ok({
                "log_id": str(open_log["id"]),
                "stardate": open_log["stardate"],
                "entry_count": 0,
                "status": "pending",
                "message": (
                    "Log closed with no entries — there is nothing in it but the closing summary. "
                    "Next time, append as you go."
                ),
            })

        log.info("captains_log_end", id=str(open_log["id"]), entries=result["entry_count"])
        return ToolResult.ok({
            "log_id": str(open_log["id"]),
            "stardate": open_log["stardate"],
            "title": open_log["title"],
            "entry_count": result["entry_count"],
            "status": "pending",
            "message": (
                f"Log closed — stardate {open_log['stardate']}, {result['entry_count']} entries "
                "compiled into a document. Tell the owner plainly: this is by proposal only, it is "
                "waiting for their approval in the admin panel, and its contents expire in "
                f"{PENDING_TTL_HOURS} hours if they don't approve it."
            ),
        })
