# Captain's Log — Claude Context

This repo is an **instar skill**: it installs into project-instar's tool-executor as
`tool-executor/src/tools/captains_log/`. It is NOT part of project-instar and nothing from
it belongs in project-instar's git. Author and commit **here**; the installed copy is a
deploy artifact and gets overwritten.

This repo is **public**. Keep employer names, hostnames, real people, and infrastructure
details out of it — examples in docs and tool descriptions are invented on purpose.

## What this skill is

A log is a **container** with ordered, typed contents and a lifecycle. That is the whole
reason it is not another scope in the recall skill: recall is one row per fact, reviewed in
a truncated table. This needs a document viewer, and a skill gets exactly one admin surface
(`admin: type: review` **or** `admin_panel:` + `admin_api:`, never both).

```
captains_log_begin   -> open a log, one per speaker
captains_log_append  -> one typed, summarized fragment (+ a required `why`)
captains_log_end     -> compile to markdown + JSON, status pending, owner approves
captains_log_status  -> is one open, what's in it
captains_log_search  -> approved logs by text / tags / stardate prefix
captains_log_read    -> one approved log in full
```

## Where the rules live

`_log.py` — not spread across the tools. `begin`, `append`, `end`, the sweep, and the admin
API all enforce the same ones from there: `stardate()`, `sweep()`, `get_open_log()`,
`compile_document()`, `close_log()`, `VALID_KINDS`, and the two TTL constants.

If you are changing behavior, it is almost certainly a change to `_log.py`, not to a tool.

## Invariants — do not quietly break these

- **One open log per speaker**, enforced by a partial unique index in the migration, not by
  the model behaving. A reconnect that mints a new session must not fork the conversation
  into two logs. `get_open_log()` therefore keys on `speaker_id` first and falls back to
  `session_id` only for a null speaker.
- **Speaker identity is server-resolved** (`_speaker.py` → gatekeeper `/session-info`) and
  never bot-supplied. A tool argument for "who is talking" would let one person append to or
  read another's log. There is no such argument. Do not add one.
- **Abandoned is not deleted.** An open log idle past `ABANDON_AFTER_HOURS` is closed,
  compiled from what it has, and still sent for review. Losing an hour of conversation to a
  dropped socket is the failure mode this design exists to prevent — do not "clean up" stale
  logs by dropping them.
- **Only `approved` logs are readable** by `captains_log_read` / `captains_log_search`.
  Pending and abandoned logs are visible to the owner in the panel and to nobody else.
- **Compile happens once, in `close_log()`.** `compiled` (JSON) is the source of truth;
  `compiled_md` is what the owner reads and may be hand-edited before approval. Do not
  re-compile from entries after a log closes — that would silently discard those edits.
- The lifecycle sweep is **lazy** — it runs on `begin`, `status`, and the panel's list/Sweep.
  No cron to install and none should be added.

## Framework facts worth knowing (learned the annoying way)

- Skill admin routes are proxied `/api/{skill}/…` → tool-executor `/skill_api/{skill}/…`
  and dispatched against the `routes` table at the bottom of `admin_api.py`.
- **Query strings are stripped before routing, and GET bodies are not parsed.** So list
  endpoints return everything and `admin.html` filters client-side. Adding `?status=pending`
  will not work; it will silently match nothing.
- Handler signature is `async handler(pool, body=None, credentials=None, **regex_groups)`.
  Return a JSON-serializable dict; `__status` sets a non-200 code.
- Migrations under `migrations/` run automatically on install and must be idempotent — they
  re-run. Everything here is `IF NOT EXISTS`.
- The tool base class hands you `self._session_id`, `self._gatekeeper_url`,
  `self._profile_slug`, and `_conversation_id` in kwargs.

## Gotchas

- `stardate()` uses **local** server time. Ten slots a day; it is a designation, not a
  timestamp — `started_at` is the timestamp.
- Entry `kind` is a closed enum in `_log.py`. Adding one means adding it to `VALID_KINDS`,
  `_SECTION_ORDER`, and `_SECTION_TITLES`, or entries land in the "Other" bucket.
- `compiled` comes back from asyncpg as a JSON **string**, not a dict. Fine for the API
  response; parse it if you ever consume it server-side.
- `captains_log_begin`'s duplicate check is deliberately server-side. Do not move it into
  instruction text — the point is that it does not depend on the model remembering to look.

## Testing

There is no harness yet. Minimum before pushing: `python3 -c "import ast,glob;
[ast.parse(open(f).read()) for f in glob.glob('*.py')]"`, and read `migrations/*.sql` for
idempotency. Real verification means installing the zip on a box and driving a log through
begin → append → end → approve → read.
