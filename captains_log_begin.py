"""
captains_log_begin — open a captain's log.

From the moment this returns, the conversation is being written down: every few turns the
bot summarizes what was said into the log with captains_log_append, and captains_log_end
compiles it into a document for the owner to approve.
"""

import structlog

from ..base import BaseTool, ToolResult
from ..registry import register_tool
from ._speaker import resolve_speaker
from ._log import PENDING_TTL_HOURS, get_open_log, opening_line, stardate, sweep

log = structlog.get_logger()


@register_tool
class CaptainsLogBeginTool(BaseTool):
    """Open a new captain's log (or hand back the one already open)."""

    @property
    def name(self) -> str:
        return "captains_log_begin"

    @property
    def short_description(self) -> str:
        return "Begin a captain's log"

    @property
    def description(self) -> str:
        return (
            "Open a CAPTAIN'S LOG. Call this the moment the owner says 'begin captain's log', "
            "'start a log', 'log this conversation', or otherwise asks you to write up what you "
            "are about to talk about — call it BEFORE you reply to them. "
            "While a log is open, you summarize the conversation into it with captains_log_append "
            "every few turns, and close it with captains_log_end. "
            "Tag it so it can be found later: 'stardate' for a general daily journal, 'project' "
            "for a project you are designing or discussing, plus whatever names the subject "
            "(e.g. 'roblox', 'instar'). If a similar log already exists, this returns it under "
            "possible_duplicates — tell the owner and ask whether to continue that one "
            "(pass its stardate as continue_from) instead of starting fresh. "
            "Only one log can be open at a time; if one already is, this returns that one."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "What this log is about, as a headline. Specific: 'Dave's inventory app — first design pass', not 'Project chat'.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for finding it later. Use 'stardate' for a general daily journal entry, 'project' for a project discussion, plus subject tags.",
                },
                "purpose": {
                    "type": "string",
                    "description": "Why this log is being opened and what it should capture. The owner reads this when deciding whether to approve.",
                },
                "continue_from": {
                    "type": "string",
                    "description": "Stardate (or id) of an earlier log this one continues. Use when the owner is picking a previous conversation back up.",
                },
            },
            "required": ["title"],
        }

    def credential_keys(self) -> list[str]:
        return []

    async def execute(
        self,
        title: str,
        tags: list[str] = None,
        purpose: str = "",
        continue_from: str = "",
        **kwargs,
    ) -> ToolResult:
        from ...db import get_pool

        pool = get_pool()
        if not pool:
            return ToolResult.fail("Database not available — the captains_log skill requires database configuration")

        tags = [t.strip().lower() for t in (tags or []) if t and t.strip()]
        who = await resolve_speaker(self)

        async with pool.acquire() as conn:
            await sweep(conn)

            existing = await get_open_log(conn, who["speaker_id"], who["session_id"])
            if existing:
                return ToolResult.ok({
                    "log_id": str(existing["id"]),
                    "stardate": existing["stardate"],
                    "title": existing["title"],
                    "already_open": True,
                    "entry_count": existing["entry_count"],
                    "message": (
                        f"A log is already open: '{existing['title']}' (stardate {existing['stardate']}), "
                        f"{existing['entry_count']} entries. Keep appending to it, or close it with "
                        "captains_log_end before starting another."
                    ),
                })

            parent_id, parent_label = None, None
            if continue_from:
                parent = await conn.fetchrow(
                    """SELECT id, stardate, title FROM captains_logs
                       WHERE (stardate = $1 OR id::text = $1)
                         AND status IN ('approved', 'pending', 'abandoned')
                       ORDER BY started_at DESC LIMIT 1""",
                    continue_from.strip(),
                )
                if parent:
                    parent_id = parent["id"]
                    parent_label = f"{parent['stardate']} — {parent['title']}"

            # Has this ground been covered? Server-side, so it does not depend on the model
            # remembering to look. Title words or shared tags, most recent first.
            dupes = await conn.fetch(
                """SELECT stardate, title, status, tags, started_at
                   FROM captains_logs
                   WHERE status IN ('approved', 'pending')
                     AND (title ILIKE $1 OR tags && $2::text[])
                   ORDER BY started_at DESC LIMIT 5""",
                f"%{title.strip()[:40]}%",
                [t for t in tags if t not in ("stardate", "project")] or [""],
            )

            sd = stardate()
            row = await conn.fetchrow(
                """INSERT INTO captains_logs
                       (stardate, title, tags, status, purpose, profile_slug,
                        speaker_id, speaker_label, source_interface, session_id, parent_id)
                   VALUES ($1, $2, $3, 'open', $4, $5, $6, $7, $8, $9, $10)
                   RETURNING id""",
                sd, title.strip(), tags, purpose, getattr(self, "_profile_slug", None),
                who["speaker_id"], who["speaker_label"], who["source_interface"],
                who["session_id"], parent_id,
            )

        log.info("captains_log_begin", id=str(row["id"]), stardate=sd, speaker=who["speaker_id"])
        return ToolResult.ok({
            "log_id": str(row["id"]),
            "stardate": sd,
            "title": title.strip(),
            "tags": tags,
            "continues": parent_label,
            "opening_line": opening_line(sd, title.strip()),
            "possible_duplicates": [
                {
                    "stardate": d["stardate"],
                    "title": d["title"],
                    "status": d["status"],
                    "tags": list(d["tags"]) if d["tags"] else [],
                }
                for d in dupes
            ],
            "message": (
                f"Log open — stardate {sd}. Append a summary of the conversation every few turns "
                "with captains_log_append (summaries, never transcript), and close it with "
                f"captains_log_end. It is a PROPOSAL: it is kept only if the owner approves it, and "
                f"it expires {PENDING_TTL_HOURS} hours after it closes if they don't."
            ),
        })
