"""
Resolve WHO is speaking from the authenticated session — never from bot-supplied input.

Same contract as the recall skill: a log belongs to a person, and the model must not be
able to claim to be someone else, or one speaker could append to (or read) another's log.
Identity comes from the gatekeeper's /session-info for the session it minted.
"""

import structlog

log = structlog.get_logger()


async def resolve_speaker(tool) -> dict:
    """Return {speaker_id, speaker_label, source_interface, session_id} for the current session.

    Degrades to a null speaker rather than trusting anything the bot supplied. A null
    speaker can still open a log (it just isn't tied to a person for resume/search).
    """
    session_id = getattr(tool, "_session_id", None)
    gk = getattr(tool, "_gatekeeper_url", None)
    out = {
        "speaker_id": None,
        "speaker_label": None,
        "source_interface": None,
        "session_id": session_id,
    }
    if not session_id or not gk:
        return out
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gk}/session-info", params={"session_id": session_id}, timeout=5.0
            )
        if resp.status_code != 200:
            return out
        info = resp.json() or {}
        source = info.get("source") or ""
        user_id = info.get("user_id") or ""
        if source and user_id:
            out["speaker_id"] = f"{source}:{user_id}"
            out["speaker_label"] = info.get("user_label") or user_id
            out["source_interface"] = source
    except Exception as e:
        log.warning("captains_log_resolve_speaker_failed", error=str(e))
    return out
