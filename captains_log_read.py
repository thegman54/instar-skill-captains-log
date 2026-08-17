"""
captains_log_read — read one approved log in full.

This is what makes a log worth writing: months later the owner says "pull up what we
worked out for Dave's app" and the decisions, requirements and open questions come back
structured, not as a wall of chat.
"""

import structlog

from ..base import BaseTool, ToolResult
from ..registry import register_tool
from ._log import fetch_entries

log = structlog.get_logger()


@register_tool
class CaptainsLogReadTool(BaseTool):
    """Read the full compiled contents of an approved captain's log."""

    @property
    def name(self) -> str:
        return "captains_log_read"

    @property
    def short_description(self) -> str:
        return "Read a captain's log in full"

    @property
    def description(self) -> str:
        return (
            "Read one approved captain's log in full — its decisions, requirements, open questions, "
            "risks and next steps, grouped by kind. Identify it by stardate (preferred) or log_id, "
            "both of which come from captains_log_search. "
            "Use it when picking a logged conversation back up: read the log FIRST, then talk — the "
            "open questions in it are where the conversation should resume. "
            "If the owner then wants to continue that work in a new log, pass its stardate to "
            "captains_log_begin as continue_from so the two are linked."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "stardate": {
                    "type": "string",
                    "description": "The log's stardate, e.g. '20260813.8'. Use this or log_id.",
                },
                "log_id": {
                    "type": "string",
                    "description": "The log's id. Use this or stardate.",
                },
            },
            "required": [],
        }

    def credential_keys(self) -> list[str]:
        return []

    async def execute(self, stardate: str = "", log_id: str = "", **kwargs) -> ToolResult:
        from ...db import get_pool

        pool = get_pool()
        if not pool:
            return ToolResult.fail("Database not available — the captains_log skill requires database configuration")

        ident = (stardate or log_id or "").strip()
        if not ident:
            return ToolResult.fail("Give a stardate or a log_id — use captains_log_search to find one.")

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, stardate, title, tags, status, purpose, closing, compiled,
                          compiled_md, entry_count, started_at, parent_id
                   FROM captains_logs
                   WHERE (stardate = $1 OR id::text = $1)
                   ORDER BY started_at DESC LIMIT 1""",
                ident,
            )
            if not row:
                return ToolResult.fail(
                    f"No captain's log found for '{ident}'. Use captains_log_search to find the right one."
                )
            if row["status"] != "approved":
                return ToolResult.fail(
                    f"Log '{row['stardate']}' is {row['status']}, not approved — you cannot read it. "
                    "Only logs the owner has approved are readable. Do not describe its contents."
                )
            entries = await fetch_entries(conn, row["id"])
            parent = None
            if row["parent_id"]:
                p = await conn.fetchrow(
                    "SELECT stardate, title FROM captains_logs WHERE id = $1", row["parent_id"]
                )
                if p:
                    parent = {"stardate": p["stardate"], "title": p["title"]}

        sections: dict[str, list] = {}
        for e in entries:
            sections.setdefault(e["kind"], []).append({"content": e["content"], "why": e["why"]})

        return ToolResult.ok({
            "log_id": str(row["id"]),
            "stardate": row["stardate"],
            "title": row["title"],
            "tags": list(row["tags"]) if row["tags"] else [],
            "purpose": row["purpose"],
            "closing": row["closing"],
            "continues": parent,
            "entry_count": row["entry_count"],
            "logged_at": row["started_at"].isoformat() if row["started_at"] else None,
            "sections": sections,
            "markdown": row["compiled_md"],
        })
