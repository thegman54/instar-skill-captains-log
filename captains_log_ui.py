"""
captains_log_ui — put the log's OWN interface on the visitor's page, and fill it.

Why this is a tool and not something the model composes
-------------------------------------------------------
The interface is `bot.html`, shipped in this skill. This tool reads that file off disk
and posts it to the relay. **The model never sees the markup.** That is the whole point:

* A page of HTML in the model's context, every turn, is an absurd way to draw a list.
* A model free-handing its own interface draws it slightly differently every time, so a
  person never learns where anything is.
* The parts of a screen that must not drift — what a press means, what is clickable,
  how a recording log is marked — stop being a decision made under time pressure.

So the split is: this skill owns what the log LOOKS like, and the model owns what the
log SAYS. Mounting costs the model one call with no arguments; filling it costs a small
JSON object.

The frame runs under `sandbox="allow-scripts"` with no `allow-same-origin`, so it has an
opaque origin and cannot touch the host page, its storage or its socket. Its only channel
is postMessage, and the host treats what arrives as a claim — the same standing as a
button press. Shipping an interface is not a way to get more authority than that.
"""

from pathlib import Path
from typing import Any, Optional

import httpx
import structlog

from ..base import BaseTool, ToolResult
from ..registry import register_tool

log = structlog.get_logger()

DEFAULT_RELAY = "https://relay.registerabot.com"


def _relay_origin(value: Optional[str]) -> str:
    """The relay's HTTP origin.

    REGISTERABOT_RELAY_URL is shared with the interface, which needs the SOCKET url and
    is set to wss:// in Infisical. Posting is HTTPS, so the scheme has to be normalised
    or the request goes nowhere with a confusing error.
    """
    url = (value or DEFAULT_RELAY).strip().rstrip("/")
    if url.startswith("wss://"):
        url = "https://" + url[len("wss://"):]
    elif url.startswith("ws://"):
        url = "http://" + url[len("ws://"):]
    return url


TOOL_ID = "captains_log"
TITLE = "Captain's Log"
# Mirrors TOOL_HTML_MAX in relay/src/chat-surface.ts. Over this the page drops it
# silently, so refuse here where there is somewhere to say why.
HTML_MAX = 400_000


def _bot_html() -> str:
    return (Path(__file__).parent / "bot.html").read_text(encoding="utf-8")


@register_tool
class CaptainsLogUiTool(BaseTool):
    """Open the captain's log interface on the visitor's page."""

    @property
    def name(self) -> str:
        return "captains_log_ui"

    @property
    def short_description(self) -> str:
        return "Open the captain's log interface on the page"

    @property
    def description(self) -> str:
        return (
            "Put the captain's log's own interface on the visitor's page, and fill it "
            "with results. Use it when they ask to OPEN the log, search their logs, or "
            "read one — on a chat surface this replaces describing logs out loud.\n\n"
            "Call with no arguments to open it. Then call it again with `hits` after a "
            "search, or `log` after a read, to put the data on screen. The interface is "
            "already written and ships with this skill: you never describe its layout, "
            "and there is no HTML for you to produce.\n\n"
            "It sends presses back to you as ui_event:\n"
            "  search_logs  — they typed a query (`value` is the text; may be empty)\n"
            "  open_log     — they picked a log (`value` is its stardate/id)\n"
            "  ui_ready     — the interface finished loading and wants its first fill\n"
            "Answer a press by calling the matching log tool and sending the result "
            "back through here. A press is a request, checked like any other: it does "
            "not bypass approval, and an open log still refuses to be read."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "hits": {
                    "type": "array",
                    "description": (
                        "Search results to list, from captains_log_search. Each: "
                        "{id (stardate), title, stardate?, entries?, tags?, open?}. "
                        "Send [] to show 'nothing matched' rather than leaving stale "
                        "results on screen."
                    ),
                    "items": {"type": "object"},
                },
                "query": {
                    "type": "string",
                    "description": "The query these hits answer, echoed into the field.",
                },
                "log": {
                    "type": "object",
                    "description": (
                        "One log to display, from captains_log_read (or the `open` "
                        "block of captains_log_status for a log still recording). "
                        "{id, title, stardate?, entries?, tags?, open?, sections:[...]}"
                        " — sections are the same shape the read tool returns."
                    ),
                },
            },
        }

    def credential_keys(self) -> list[str]:
        return [self._binding_key(), "REGISTERABOT_RELAY_URL"]

    # ---- plumbing ---------------------------------------------------------------

    def _binding_key(self) -> str:
        slug = (self._profile_slug or "").strip().upper().replace("-", "_")
        return f"BINDING_REGISTERABOT_{slug}_API_KEY" if slug else "REGISTERABOT_API_KEY"

    async def _relay_session_id(self) -> Optional[str]:
        """The visitor's relay session, recovered from this tool's session.

        The registerabot adapter sets conversation_id to 'registerabot:{relay_session}'.
        A conversation from anywhere else has no page, and this returns None.
        """
        if not self._session_id or not self._gatekeeper_url:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self._gatekeeper_url}/session-info",
                                     params={"session_id": self._session_id})
                if r.status_code != 200:
                    return None
                conv = (r.json() or {}).get("conversation_id") or ""
        except Exception as e:                                        # noqa: BLE001
            log.warning("captains_log_ui_session_lookup_failed", error=str(e))
            return None
        prefix = "registerabot:"
        return conv[len(prefix):] if conv.startswith(prefix) else None

    async def execute(self, hits: list = None, query: str = None,
                      log_: dict = None, **kwargs) -> ToolResult:
        # `log` collides with the module-level logger, so it arrives in kwargs.
        one = kwargs.get("log") if kwargs.get("log") is not None else log_

        slug = self._profile_slug
        if not slug:
            return ToolResult.fail("No profile slug on this session.")

        session_id = await self._relay_session_id()
        if not session_id:
            return ToolResult.fail(
                "This conversation is not on a chat surface, so there is no page to "
                "open. Describe the logs in words instead.")

        ops: list[dict] = []

        # Mount on the first call of a conversation, and on any call that is only
        # opening. Re-mounting on every fill would reload the frame and throw away
        # what they had scrolled to.
        if hits is None and one is None:
            try:
                html = _bot_html()
            except OSError as e:
                return ToolResult.fail(f"Could not read the interface file: {e}")
            if len(html) > HTML_MAX:
                return ToolResult.fail(
                    f"bot.html is {len(html)} bytes; the page drops anything over "
                    f"{HTML_MAX}.")
            ops.append({"op": "tool_ui", "id": TOOL_ID, "title": TITLE, "html": html})
        else:
            data: dict[str, Any] = {}
            if query is not None:
                data["query"] = str(query)[:200]
            if hits is not None:
                data["hits"] = [self._clean_hit(h) for h in list(hits)[:200]]
            if one is not None:
                data["log"] = self._clean_log(one)
            ops.append({"op": "tool_data", "id": TOOL_ID, "data": data})

        api_key = self.get_credential(self._binding_key())
        if not api_key:
            return ToolResult.fail(f"{self._binding_key()} is not set.")
        relay = _relay_origin(self.get_credential("REGISTERABOT_RELAY_URL"))

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{relay}/bots/{slug}/ui",
                    json={"session_id": session_id, "ops": ops},
                    headers={"Authorization": f"Bearer {api_key}",
                             "Content-Type": "application/json"},
                )
        except Exception as e:                                        # noqa: BLE001
            return ToolResult.fail(f"Could not reach the relay: {e}")

        if resp.status_code != 200:
            return ToolResult.fail(
                f"Relay returned {resp.status_code}: {resp.text[:250]}")

        mounted = ops[0]["op"] == "tool_ui"
        log.info("captains_log_ui", slug=slug, mounted=mounted,
                 hits=len(hits) if hits is not None else None,
                 has_log=one is not None, session=session_id[:8])

        if mounted:
            return ToolResult.ok({
                "status": "interface open on the visitor's page, and EMPTY",
                "next": (
                    "Fill it NOW, in this same turn: captains_log_search (no query "
                    "gives the most recent) and send the results straight back through "
                    "captains_log_ui. Do not wait for anything first — an empty window "
                    "with you saying you are waiting on it is worse than no window."
                ),
                "note": (
                    "ui_ready is a nudge, not a gate. It arrives when the interface has "
                    "loaded and is only useful if you had nothing to show yet; anything "
                    "you send before it is held and delivered. Never wait on it. "
                    "Do not describe the layout either — they can see it."
                ),
            })
        return ToolResult.ok({
            "status": "on the visitor's page",
            "showing": {"hits": len(hits) if hits is not None else None,
                        "log": (one or {}).get("title") if one else None},
            "note": ("Say the thing the screen cannot: which one matters, or that the "
                     "one they wanted is not there. Do not read the rows back."),
        })

    # ---- shaping ----------------------------------------------------------------

    @staticmethod
    def _clean_hit(h: Any) -> dict:
        h = h if isinstance(h, dict) else {}
        out = {
            "id": str(h.get("id") or h.get("stardate") or "")[:64],
            "title": str(h.get("title") or "Untitled log")[:200],
        }
        if h.get("stardate"):
            out["stardate"] = str(h["stardate"])[:32]
        if h.get("entries") is not None:
            try:
                out["entries"] = int(h["entries"])
            except (TypeError, ValueError):
                pass
        tags = h.get("tags")
        if isinstance(tags, list) and tags:
            out["tags"] = [str(t)[:40] for t in tags[:6]]
        if h.get("open"):
            out["open"] = True
        return out

    @classmethod
    def _clean_log(cls, g: Any) -> dict:
        g = g if isinstance(g, dict) else {}
        out = cls._clean_hit(g)
        secs = []
        for s in (g.get("sections") or [])[:40]:
            s = s if isinstance(s, dict) else {}
            sec: dict[str, Any] = {}
            if s.get("heading"):
                sec["heading"] = str(s["heading"])[:120]
            if s.get("body"):
                sec["body"] = str(s["body"])[:4000]
            items = s.get("items")
            if isinstance(items, list) and items:
                sec["items"] = [str(i)[:1000] for i in items[:120]]
            if sec:
                secs.append(sec)
        out["sections"] = secs
        return out
