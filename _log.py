"""
Shared internals for the Captain's Log skill: stardates, lifecycle sweep, and compilation.

Nothing here is bot-facing. The tools are thin; the rules live here so `begin`, `append`,
`end`, and the admin API all enforce exactly the same ones.
"""

from datetime import datetime, timezone

import structlog

log = structlog.get_logger()

# How long an unreviewed (pending) log survives before it expires. Matches recall's
# proposal contract — the owner approves it or it goes away.
PENDING_TTL_HOURS = 48

# How long an *open* log may sit with no new entries before it is considered abandoned.
# Abandoned is NOT deleted: on the road a dropped socket or a dead phone must not cost an
# hour of conversation, so the log is closed, compiled from what it has, and still shows up
# for review until it expires like any other proposal.
ABANDON_AFTER_HOURS = 12

VALID_KINDS = (
    "context",        # background — what this is, who's involved, where it stands
    "requirement",    # something that must be true of the thing being designed
    "decision",       # a call that was made, and ideally why
    "open_question",  # unresolved, needs an answer before building
    "risk",           # what could go wrong / what worries us
    "idea",           # a possibility, not yet a decision
    "todo",           # a concrete action for someone
    "quote",          # something said verbatim that's worth keeping exactly
    "next_step",      # what happens next, in order
)

# Order sections appear in the compiled document — the shape of a useful write-up, not
# the order things happened to be said in.
_SECTION_ORDER = (
    "context", "requirement", "decision", "open_question",
    "risk", "idea", "todo", "next_step", "quote",
)

_SECTION_TITLES = {
    "context": "Context",
    "requirement": "Requirements",
    "decision": "Decisions",
    "open_question": "Open Questions",
    "risk": "Risks",
    "idea": "Ideas",
    "todo": "To Do",
    "next_step": "Next Steps",
    "quote": "Verbatim",
}


def stardate(dt: datetime | None = None) -> str:
    """`20260813.8` — the calendar day plus which tenth of that day it is.

    Not the real Star Trek formula (which nobody agrees on anyway); this one sorts
    lexically, reads as a date, and gives ten distinguishable slots per day so more than
    one log a day still has a distinct designation.
    """
    dt = dt or datetime.now().astimezone()
    seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
    tenth = min(9, seconds * 10 // 86400)
    return f"{dt:%Y%m%d}.{tenth}"


def opening_line(sd: str, title: str) -> str:
    return f"Captain's log, stardate {sd}. {title}."


async def sweep(conn) -> dict:
    """Advance the lifecycle for logs that time out. Cheap, idempotent, called on
    every begin/status and by the admin panel — no cron to forget to install.

    - open logs idle past ABANDON_AFTER_HOURS  -> abandoned (compiled from what exists)
    - pending/abandoned logs past expires_at   -> expired
    """
    stale = await conn.fetch(
        f"""SELECT id FROM captains_logs
            WHERE status = 'open'
              AND GREATEST(started_at,
                           COALESCE((SELECT max(created_at) FROM captains_log_entries e
                                      WHERE e.log_id = captains_logs.id), started_at))
                  < now() - INTERVAL '{ABANDON_AFTER_HOURS} hours'"""
    )
    for row in stale:
        await close_log(conn, row["id"], closing=None, status="abandoned")

    expired = await conn.fetch(
        """UPDATE captains_logs SET status = 'expired'
           WHERE status IN ('pending', 'abandoned')
             AND expires_at IS NOT NULL AND expires_at < now()
           RETURNING id"""
    )
    result = {"abandoned": len(stale), "expired": len(expired)}
    if stale or expired:
        log.info("captains_log_sweep", **result)
    return result


async def get_open_log(conn, speaker_id: str | None, session_id: str | None):
    """The caller's currently open log, if any. Keyed on speaker first (survives a
    reconnect that mints a new session), falling back to session for a null speaker."""
    if speaker_id:
        return await conn.fetchrow(
            "SELECT * FROM captains_logs WHERE speaker_id = $1 AND status = 'open'",
            speaker_id,
        )
    if session_id:
        return await conn.fetchrow(
            """SELECT * FROM captains_logs
               WHERE session_id = $1 AND speaker_id IS NULL AND status = 'open'
               ORDER BY started_at DESC LIMIT 1""",
            session_id,
        )
    return None


async def fetch_entries(conn, log_id) -> list[dict]:
    rows = await conn.fetch(
        """SELECT seq, kind, content, why, tags, detail, created_at
           FROM captains_log_entries WHERE log_id = $1 ORDER BY seq""",
        log_id,
    )
    return [
        {
            "seq": r["seq"],
            "kind": r["kind"],
            "content": r["content"],
            "why": r["why"],
            "tags": list(r["tags"]) if r["tags"] else [],
            "detail": r["detail"],
            "at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


def compile_document(log_row, entries: list[dict]) -> tuple[dict, str]:
    """Turn the fragments into the document. Returns (json, markdown).

    JSON is the source of truth — it stays structured so a future session can read the
    decisions back without re-parsing prose. The markdown is what the owner reads.
    """
    tags = list(log_row["tags"]) if log_row["tags"] else []
    doc = {
        "stardate": log_row["stardate"],
        "title": log_row["title"],
        "tags": tags,
        "purpose": log_row["purpose"],
        "closing": log_row["closing"],
        "speaker": log_row["speaker_label"],
        "interface": log_row["source_interface"],
        "started_at": log_row["started_at"].isoformat() if log_row["started_at"] else None,
        "entry_count": len(entries),
        "sections": {},
        "entries": entries,
    }
    for kind in _SECTION_ORDER:
        items = [e for e in entries if e["kind"] == kind]
        if items:
            doc["sections"][kind] = items

    lines = [
        f"# Captain's Log — {log_row['stardate']}",
        "",
        f"**{log_row['title']}**",
        "",
    ]
    meta = []
    if log_row["speaker_label"]:
        meta.append(f"Logged by {log_row['speaker_label']}")
    if log_row["source_interface"]:
        meta.append(f"via {log_row['source_interface']}")
    if log_row["started_at"]:
        meta.append(log_row["started_at"].strftime("%Y-%m-%d %H:%M"))
    if meta:
        lines += ["_" + " · ".join(meta) + "_", ""]
    if tags:
        lines += ["Tags: " + ", ".join(f"`{t}`" for t in tags), ""]
    if log_row["purpose"]:
        lines += ["> " + log_row["purpose"], ""]

    for kind in _SECTION_ORDER:
        items = doc["sections"].get(kind)
        if not items:
            continue
        lines += [f"## {_SECTION_TITLES[kind]}", ""]
        for e in items:
            lines.append(f"- {e['content']}")
            if e["why"]:
                lines.append(f"  - _why:_ {e['why']}")
        lines.append("")

    if log_row["closing"]:
        lines += ["## Closing", "", log_row["closing"], ""]

    unknown = [e for e in entries if e["kind"] not in _SECTION_ORDER]
    if unknown:
        lines += ["## Other", ""] + [f"- ({e['kind']}) {e['content']}" for e in unknown] + [""]

    return doc, "\n".join(lines)


async def close_log(conn, log_id, closing: str | None, status: str = "pending") -> dict:
    """Compile a log and move it out of `open`. Used by end (pending) and sweep (abandoned)."""
    if closing is not None:
        await conn.execute(
            "UPDATE captains_logs SET closing = $2 WHERE id = $1", log_id, closing
        )
    row = await conn.fetchrow("SELECT * FROM captains_logs WHERE id = $1", log_id)
    if not row:
        return {}
    entries = await fetch_entries(conn, log_id)
    doc, md = compile_document(row, entries)
    await conn.execute(
        f"""UPDATE captains_logs
            SET status = $2, compiled = $3::jsonb, compiled_md = $4,
                entry_count = $5, ended_at = now(),
                expires_at = now() + INTERVAL '{PENDING_TTL_HOURS} hours'
            WHERE id = $1""",
        log_id, status, _json(doc), md, len(entries),
    )
    return {"doc": doc, "markdown": md, "entry_count": len(entries)}


def _json(obj) -> str:
    import json
    return json.dumps(obj, default=str)
