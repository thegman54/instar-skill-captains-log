"""
captains_log_append — add one summarized fragment to the open log.

The log is a document, not a recording. Each fragment is a typed, self-contained summary
of something that was established — plus a `why` that says what it is doing in the log.
The `why` is not paperwork: it is what forces a fragment to be a conclusion rather than a
paraphrase of the last thing said.
"""

import json

import structlog

from ..base import BaseTool, ToolResult
from ..registry import register_tool
from ._speaker import resolve_speaker
from ._log import VALID_KINDS, get_open_log

log = structlog.get_logger()


@register_tool
class CaptainsLogAppendTool(BaseTool):
    """Append a summarized entry to the currently open captain's log."""

    @property
    def name(self) -> str:
        return "captains_log_append"

    @property
    def short_description(self) -> str:
        return "Add an entry to the open log"

    @property
    def description(self) -> str:
        return (
            "Add one entry to the OPEN captain's log. Call this as the conversation goes — every "
            "few turns, and always after something is actually settled — not once at the end. "
            "Write a SUMMARY in your own words, self-contained enough to make sense months later "
            "with none of this conversation around it. Do NOT paste the transcript, and do not log "
            "small talk. One idea per call; several calls in a row is normal and correct. "
            "Pick the `kind` honestly — a decision is a decision, a maybe is an idea — because the "
            "compiled document is grouped by kind, and that grouping is what makes it useful later. "
            "Every entry needs a `why`: what this fragment is doing in the log."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": list(VALID_KINDS),
                    "description": (
                        "context = background/where things stand; requirement = must be true; "
                        "decision = a call that was made; open_question = unresolved; risk = what "
                        "could go wrong; idea = a possibility, not decided; todo = an action for "
                        "someone; quote = worth keeping verbatim; next_step = what happens next."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "The summary. Self-contained, specific, past tense. For 'quote', the exact words.",
                },
                "why": {
                    "type": "string",
                    "description": "Why this belongs in the log — what it settles, unblocks, or constrains. Required.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for this entry (the log carries its own tags too).",
                },
                "detail": {
                    "type": "object",
                    "description": "Optional structured extras — owner, deadline, url, alternatives considered, etc.",
                },
            },
            "required": ["kind", "content", "why"],
        }

    def credential_keys(self) -> list[str]:
        return []

    async def execute(
        self,
        kind: str,
        content: str,
        why: str,
        tags: list[str] = None,
        detail: dict = None,
        **kwargs,
    ) -> ToolResult:
        from ...db import get_pool

        pool = get_pool()
        if not pool:
            return ToolResult.fail("Database not available — the captains_log skill requires database configuration")

        kind = (kind or "").strip().lower()
        if kind not in VALID_KINDS:
            return ToolResult.fail(
                f"'{kind}' is not a log entry kind. Use one of: {', '.join(VALID_KINDS)}."
            )
        if not (content or "").strip():
            return ToolResult.fail("content is empty — there is nothing to log.")

        who = await resolve_speaker(self)
        tags = [t.strip().lower() for t in (tags or []) if t and t.strip()]

        async with pool.acquire() as conn:
            open_log = await get_open_log(conn, who["speaker_id"], who["session_id"])
            if not open_log:
                return ToolResult.fail(
                    "No captain's log is open. Call captains_log_begin first — and do not "
                    "invent one silently; opening a log is the owner's call, not yours."
                )

            seq = await conn.fetchval(
                "SELECT COALESCE(max(seq), 0) + 1 FROM captains_log_entries WHERE log_id = $1",
                open_log["id"],
            )
            await conn.execute(
                """INSERT INTO captains_log_entries (log_id, seq, kind, content, why, tags, detail)
                   VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)""",
                open_log["id"], seq, kind, content.strip(), (why or "").strip(),
                tags, json.dumps(detail or {}),
            )
            await conn.execute(
                "UPDATE captains_logs SET entry_count = $2 WHERE id = $1", open_log["id"], seq
            )

        log.info("captains_log_append", id=str(open_log["id"]), seq=seq, kind=kind)
        return ToolResult.ok({
            "log_id": str(open_log["id"]),
            "stardate": open_log["stardate"],
            "seq": seq,
            "kind": kind,
            "entry_count": seq,
            "message": f"Entry {seq} recorded ({kind}). Keep going; close with captains_log_end.",
        })
