"""
captains_log_status — is a log open right now, and what is in it?

Cheap orientation call. Mid-conversation it answers "am I recording?"; at the start of a
conversation it catches the case where a log was left open on the road.
"""

import structlog

from ..base import BaseTool, ToolResult
from ..registry import register_tool
from ._speaker import resolve_speaker
from ._log import fetch_entries, get_open_log, sweep

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
            "one if you suspect an earlier conversation was cut short. Cheap — no side effects.\n\n"
            "When a log is open, `open.sections` carries the entries recorded so far, in the "
            "same shape captains_log_read returns — so you can show the owner their log "
            "filling up while it is still being dictated. captains_log_read still refuses "
            "anything unapproved; this is their own open log, in this session, shown back "
            "to them."
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
                # The entries of the log being dictated RIGHT NOW, in the same shape
                # captains_log_read returns, so the open log can be rendered as the
                # same document.
                #
                # This does NOT weaken the approval gate, and deliberately so. read
                # refuses anything unapproved because an unapproved log is a proposal
                # - the bot must not treat it as fact or show someone else's draft.
                # Neither applies here: get_open_log is scoped to THIS speaker and
                # THIS session, so it is the owner's own words, dictated moments ago,
                # being shown back to them. Still not searchable, still not readable
                # by anyone else, still requiring approval before it is a record.
                live = await fetch_entries(conn, open_log["id"])
                sections: dict[str, list] = {}
                for e in live:
                    sections.setdefault(e["kind"], []).append(
                        {"content": e["content"], "why": e["why"]})
                open_info = {
                    "log_id": str(open_log["id"]),
                    "stardate": open_log["stardate"],
                    "title": open_log["title"],
                    "tags": list(open_log["tags"]) if open_log["tags"] else [],
                    "entry_count": open_log["entry_count"],
                    "by_kind": {r["kind"]: r["n"] for r in kinds},
                    "started_at": open_log["started_at"].isoformat(),
                    "sections": sections,
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
