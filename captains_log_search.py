"""
captains_log_search — find past logs by tag or text.

Returns headlines only. Full contents come from captains_log_read, so a search never
dumps every document ever written into the conversation.
"""

import structlog

from ..base import BaseTool, ToolResult
from ..registry import register_tool

log = structlog.get_logger()


@register_tool
class CaptainsLogSearchTool(BaseTool):
    """Search past captain's logs by tags, text, or stardate."""

    @property
    def name(self) -> str:
        return "captains_log_search"

    @property
    def short_description(self) -> str:
        return "Search past captain's logs"

    @property
    def description(self) -> str:
        return (
            "Search past captain's logs. Use it whenever the owner refers to something you talked "
            "about before — a project, a conversation on the road, 'that thing we logged' — and "
            "before opening a new project log, so you continue an existing one instead of starting "
            "a duplicate. "
            "Filter by `tags` ('stardate' = daily journals, 'project' = project logs, plus subject "
            "tags), by free text, or by a `stardate` prefix like '20260813'. "
            "Returns headlines only — call captains_log_read on the one you want to actually read it. "
            "Only APPROVED logs are searchable; anything still awaiting the owner's approval, or "
            "expired, is not there and you must not claim it is."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free text — matches title, purpose, closing summary, and the compiled document.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Match logs carrying ANY of these tags.",
                },
                "stardate": {
                    "type": "string",
                    "description": "Stardate or prefix, e.g. '20260813' for that day's logs.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 10).",
                },
            },
            "required": [],
        }

    def credential_keys(self) -> list[str]:
        return []

    async def execute(
        self,
        query: str = "",
        tags: list[str] = None,
        stardate: str = "",
        limit: int = 10,
        **kwargs,
    ) -> ToolResult:
        from ...db import get_pool

        pool = get_pool()
        if not pool:
            return ToolResult.fail("Database not available — the captains_log skill requires database configuration")

        tags = [t.strip().lower() for t in (tags or []) if t and t.strip()]
        limit = max(1, min(int(limit or 10), 50))

        conditions = ["status = 'approved'"]
        params = []
        idx = 1
        if query and query.strip():
            conditions.append(
                f"(title ILIKE ${idx} OR purpose ILIKE ${idx} OR closing ILIKE ${idx} OR compiled_md ILIKE ${idx})"
            )
            params.append(f"%{query.strip()}%")
            idx += 1
        if tags:
            conditions.append(f"tags && ${idx}::text[]")
            params.append(tags)
            idx += 1
        if stardate and stardate.strip():
            conditions.append(f"stardate LIKE ${idx}")
            params.append(f"{stardate.strip()}%")
            idx += 1

        params.append(limit)
        sql = f"""SELECT id, stardate, title, tags, purpose, closing, entry_count, started_at
                  FROM captains_logs
                  WHERE {' AND '.join(conditions)}
                  ORDER BY started_at DESC
                  LIMIT ${idx}"""

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        results = [
            {
                "log_id": str(r["id"]),
                "stardate": r["stardate"],
                "title": r["title"],
                "tags": list(r["tags"]) if r["tags"] else [],
                "purpose": r["purpose"],
                "closing": r["closing"],
                "entry_count": r["entry_count"],
                "logged_at": r["started_at"].isoformat() if r["started_at"] else None,
            }
            for r in rows
        ]

        return ToolResult.ok({
            "total": len(results),
            "results": results,
            "hint": (
                "Call captains_log_read(stardate) to read one in full."
                if results else
                "Nothing matched. That means no APPROVED log matched — not that the conversation "
                "never happened. Say so plainly rather than inventing what it contained."
            ),
        })
