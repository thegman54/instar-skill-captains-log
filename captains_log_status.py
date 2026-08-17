"""
captains_log_status — is a log open right now, and what is in it?

Cheap orientation call. Mid-conversation it answers "am I recording?"; at the start of a
conversation it catches the case where a log was left open on the road.
"""

import structlog

from ..base import BaseTool, ToolResult
from ..registry import register_tool
from ._speaker import resolve_speaker
from ._log import get_open_log, sweep

log = structlog.get_logger()


@register_tool
class CaptainsLogStatusTool(BaseTool):
    """Report whether a captain's log is open, and summarize recent logs."""

    @property
    def name(self) -> str:
        return "captains_log_status"

    @property
    def short_description(self) -> str:
        return "Check for an open captain's log"

    @property
    def description(self) -> str:
        return (
            "Check whether a captain's log is currently open for this person, what is in it so far, "
            "and what their recent logs were. Call it when the owner asks whether you are logging, "
            "when they refer to 'the log' and you are not sure one is open, or before opening a new "
            "one if you suspect an earlier conversation was cut short. Cheap — no side effects."
        )

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    def credential_keys(self) -> list[str]:
        return []

    async def execute(self, **kwargs) -> ToolResult:
        from ...db import get_pool

        pool = get_pool()
        if not pool:
            return ToolResult.fail("Database not available — the captains_log skill requires database configuration")

        who = await resolve_speaker(self)

        async with pool.acquire() as conn:
            await sweep(conn)
            open_log = await get_open_log(conn, who["speaker_id"], who["session_id"])

            open_info = None
            if open_log:
                kinds = await conn.fetch(
                    "SELECT kind, count(*) AS n FROM captains_log_entries WHERE log_id = $1 GROUP BY kind",
                    open_log["id"],
                )
                open_info = {
                    "log_id": str(open_log["id"]),
                    "stardate": open_log["stardate"],
                    "title": open_log["title"],
                    "tags": list(open_log["tags"]) if open_log["tags"] else [],
                    "entry_count": open_log["entry_count"],
                    "by_kind": {r["kind"]: r["n"] for r in kinds},
                    "started_at": open_log["started_at"].isoformat(),
                }

            recent = await conn.fetch(
                """SELECT stardate, title, status, tags, entry_count, started_at
                   FROM captains_logs
                   WHERE ($1::text IS NULL OR speaker_id = $1)
                     AND status IN ('approved', 'pending', 'abandoned')
                   ORDER BY started_at DESC LIMIT 5""",
                who["speaker_id"],
            )

        return ToolResult.ok({
            "open": open_info,
            "is_logging": open_info is not None,
            "recent": [
                {
                    "stardate": r["stardate"],
                    "title": r["title"],
                    "status": r["status"],
                    "tags": list(r["tags"]) if r["tags"] else [],
                    "entry_count": r["entry_count"],
                }
                for r in recent
            ],
            "message": (
                f"Logging: '{open_info['title']}' (stardate {open_info['stardate']}), "
                f"{open_info['entry_count']} entries."
                if open_info else "No captain's log is open."
            ),
        })
