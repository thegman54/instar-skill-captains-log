"""
Captain's Log — admin API.

The skill owns its own tables and its own CRUD; project-instar only proxies
/api/captains_log/... → /skill_api/captains_log/....

Handler signature: async handler(pool, body=None, credentials=None, **regex_groups)
Returns a JSON-serializable dict. Use the __status key for non-200 responses.

Note: query strings are stripped before routing, so list endpoints return everything the
panel needs and the panel filters client-side.
"""

import structlog

from ._log import PENDING_TTL_HOURS, fetch_entries, sweep

log = structlog.get_logger()


def _iso(dt):
    return dt.isoformat() if dt else None


def _headline(r) -> dict:
    return {
        "id": str(r["id"]),
        "stardate": r["stardate"],
        "title": r["title"],
        "tags": list(r["tags"]) if r["tags"] else [],
        "status": r["status"],
        "purpose": r["purpose"],
        "closing": r["closing"],
        "speaker_label": r["speaker_label"],
        "source_interface": r["source_interface"],
        "entry_count": r["entry_count"],
        "started_at": _iso(r["started_at"]),
        "ended_at": _iso(r["ended_at"]),
        "expires_at": _iso(r["expires_at"]),
    }


async def list_logs(pool, body=None, **kw):
    """All logs, newest first, without their compiled bodies (the panel fetches those on click)."""
    async with pool.acquire() as conn:
        await sweep(conn)
        rows = await conn.fetch(
            """SELECT id, stardate, title, tags, status, purpose, closing, speaker_label,
                      source_interface, entry_count, started_at, ended_at, expires_at
               FROM captains_logs
               ORDER BY started_at DESC
               LIMIT 500"""
        )
    logs = [_headline(r) for r in rows]
    counts: dict[str, int] = {}
    all_tags: set[str] = set()
    for entry in logs:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
        all_tags.update(entry["tags"])
    return {
        "logs": logs,
        "count": len(logs),
        "counts": counts,
        "tags": sorted(all_tags),
        "pending_ttl_hours": PENDING_TTL_HOURS,
    }


async def get_log(pool, body=None, log_id=None, **kw):
    """One log, with its compiled document and raw entries."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT * FROM captains_logs WHERE id = $1::uuid OR stardate = $1""", log_id
        )
        if not row:
            return {"__status": 404, "detail": "log not found"}
        entries = await fetch_entries(conn, row["id"])
        parent = None
        if row["parent_id"]:
            p = await conn.fetchrow(
                "SELECT id, stardate, title FROM captains_logs WHERE id = $1", row["parent_id"]
            )
            if p:
                parent = {"id": str(p["id"]), "stardate": p["stardate"], "title": p["title"]}

    out = _headline(row)
    out.update({
        "markdown": row["compiled_md"],
        "compiled": row["compiled"],
        "entries": entries,
        "continues": parent,
        "session_id": row["session_id"],
        "reviewed_at": _iso(row["reviewed_at"]),
    })
    return out


async def approve_log(pool, body=None, log_id=None, **kw):
    """Approve a log: it becomes permanent and readable by the bot via captains_log_read."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE captains_logs
               SET status = 'approved', reviewed_at = now(), expires_at = NULL
               WHERE id = $1::uuid AND status IN ('pending', 'abandoned', 'rejected', 'expired')
               RETURNING id, stardate, title""",
            log_id,
        )
    if not row:
        return {"__status": 404, "detail": "log not found or already approved"}
    log.info("captains_log_approved", id=str(row["id"]), stardate=row["stardate"])
    return {"id": str(row["id"]), "status": "approved", "stardate": row["stardate"]}


async def reject_log(pool, body=None, log_id=None, **kw):
    """Reject a log. It stays visible (and recoverable) until it expires."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""UPDATE captains_logs
                SET status = 'rejected', reviewed_at = now(),
                    expires_at = COALESCE(expires_at, now() + INTERVAL '{PENDING_TTL_HOURS} hours')
                WHERE id = $1::uuid
                RETURNING id, stardate""",
            log_id,
        )
    if not row:
        return {"__status": 404, "detail": "log not found"}
    log.info("captains_log_rejected", id=str(row["id"]))
    return {"id": str(row["id"]), "status": "rejected"}


async def update_log(pool, body=None, log_id=None, **kw):
    """Edit a log's title/tags, or hand-correct the compiled markdown before approving."""
    b = body or {}
    updates, params, idx = [], [], 2
    for field in ("title", "purpose", "closing", "compiled_md"):
        if field in b:
            updates.append(f"{field} = ${idx}")
            params.append(b[field])
            idx += 1
    if "tags" in b:
        updates.append(f"tags = ${idx}::text[]")
        params.append([t.strip().lower() for t in (b["tags"] or []) if t and t.strip()])
        idx += 1
    if not updates:
        return {"__status": 400, "detail": "no fields to update"}
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE captains_logs SET {', '.join(updates)} WHERE id = $1::uuid RETURNING id",
            log_id, *params,
        )
    if not row:
        return {"__status": 404, "detail": "log not found"}
    return {"id": str(row["id"]), "updated": True}


async def delete_log(pool, body=None, log_id=None, **kw):
    """Delete a log and its entries for good."""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM captains_logs WHERE id = $1::uuid", log_id)
    log.info("captains_log_deleted", id=log_id)
    return {"deleted": True}


async def run_sweep(pool, body=None, **kw):
    """Manually advance the lifecycle (abandon stale open logs, expire unreviewed ones)."""
    async with pool.acquire() as conn:
        return await sweep(conn)


# =============================================================================
# ROUTE TABLE
# =============================================================================

routes = [
    ("GET",    r"/logs$",                                    list_logs),
    ("GET",    r"/logs/(?P<log_id>[\w.-]+)$",                get_log),
    ("PUT",    r"/logs/(?P<log_id>[\w-]+)$",                 update_log),
    ("DELETE", r"/logs/(?P<log_id>[\w-]+)$",                 delete_log),
    ("POST",   r"/logs/(?P<log_id>[\w-]+)/approve$",         approve_log),
    ("POST",   r"/logs/(?P<log_id>[\w-]+)/reject$",          reject_log),
    ("POST",   r"/sweep$",                                   run_sweep),
]
