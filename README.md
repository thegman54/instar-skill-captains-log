# Instar Skill: Captain's Log

A [Project Instar](https://github.com/thegman54/project-instar) skill that turns a
conversation into a document.

You say *"begin captain's log"*. The bot opens one, summarizes the conversation into typed
entries as you talk, and on *"end captain's log"* compiles them into a markdown document
plus structured JSON. The log is a **proposal** — you approve it in the admin panel, or it
expires after 48 hours. Approved logs are searchable by tag and readable back months later.

Built for talking through a project from the road: voice or text into Slack, and a usable
write-up waiting when you get home.

## Tools

| Tool | Description |
|---|---|
| `captains_log_begin` | Open a log — title, tags, purpose. Returns a stardate and any possible duplicates. |
| `captains_log_append` | Add one summarized entry: `kind`, `content`, and a required `reason`. |
| `captains_log_end` | Close it, compile the document, send it for approval. |
| `captains_log_status` | Is a log open? What's in it? What were the last few? |
| `captains_log_search` | Find approved logs by text, tags, or stardate prefix. |
| `captains_log_read` | Read one approved log in full, grouped by kind. |

## Entry kinds

`context` · `requirement` · `decision` · `open_question` · `risk` · `idea` · `todo` ·
`quote` · `next_step`

The kind is not decoration — the compiled document is grouped by it, which is what makes a
log worth reading later instead of scrolling a transcript.

## Stardates

`20260813.8` — the calendar day plus which tenth of the day it is. Sorts lexically, reads as
a date, and gives ten distinguishable slots per day.

## Lifecycle

```
open ──"end captain's log"──► pending ──owner approves──► approved   (permanent, searchable)
  │                              │
  │                              └──owner rejects / 48h──► rejected / expired
  │
  └──12h idle──► abandoned  (compiled from what it has, still reviewable — a dropped
                             connection on the road never costs you the conversation)
```

One open log per speaker, enforced by a partial unique index — a reconnect cannot fork the
conversation into two logs. The lifecycle sweep runs lazily on `begin` / `status` and from
the admin panel; there is no cron to install.

## Tag conventions

| Tag | Meaning |
|---|---|
| `stardate` | General daily journal — whatever happened, whatever's on your mind |
| `project` | A project being designed. `begin` checks for existing logs on the same subject and returns them as `possible_duplicates`. |
| anything else | Subject tags — `roblox`, `instar`, `work`, … |

## Admin panel

**Admin UI → Captain's Logs**: status filters, tag filters, text search, the rendered
document, edit-before-approve, approve / reject / delete, and markdown download.

## Database

`database: true`. On install, migration `001_captains_log.sql` creates:

- `captains_logs` — the container: stardate, title, tags, status, speaker, compiled document
- `captains_log_entries` — the ordered fragments

Speaker identity is resolved **server-side** from the gatekeeper's `/session-info`, never
supplied by the bot — one person cannot append to or read another's log.

## Installation

Admin UI → **Tools** → **Upload**, select a zip of this repo. Migrations run automatically.

Then create a grant bundling `captains_log_*` and give the bot `instructions.md`.

## License

MIT
