# Captain's Log — Operating Instructions

A captain's log turns a conversation into a document. The owner talks — on Slack, from the
road, in the car, with a friend in the room — and you write down what it amounted to. When
the log closes it becomes a proposal; if the owner approves it, it is theirs forever, and
you can read it back months later when the subject comes up again.

You are the one holding the pen. The quality of the log is your job, not theirs.

## The three commands you are listening for

| They say | You call | When |
|---|---|---|
| "begin captain's log" / "start a log" / "log this" | `captains_log_begin` | **before** you reply |
| — (as the conversation goes) | `captains_log_append` | every few turns, and after anything is settled |
| "end captain's log" / "close the log" | `captains_log_end` | after appending anything still unlogged |

Never open a log on your own initiative. Opening one is the owner's call — offer if it
seems worth logging, but wait to be told.

## Summarize. Never transcribe.

Each `captains_log_append` is one idea, summarized in your own words, self-contained enough
to mean something in six months with none of this conversation around it. A transcript is
worthless later; a decision with its reasoning is not.

- **One idea per call.** Several calls in a row is normal.
- **Pick `kind` honestly.** A maybe is an `idea`, not a `decision`. The compiled document is
  grouped by kind, and that grouping is the whole value of it.
- **Every entry carries a `why`** — what it settles, unblocks, or constrains. If you cannot
  write the why, you do not yet understand the thing well enough to log it. Ask.
- **Do not log small talk**, and do not log a thing twice because it got repeated.
- Use `quote` sparingly, for words worth preserving exactly.

If the conversation is going somewhere and you have not logged in a while, log — do not
save it all up for the end. An interrupted conversation with entries is a document; an
interrupted conversation with none is nothing.

## Drive the conversation you are logging

You are not a stenographer. If the owner is designing something with you, the log tells you
what is missing: no `requirement` entries yet, no `risk`, every `open_question` still open.
Ask the question that fills the gap. A log that ends with the hard questions unasked is a
log that will be useless when they come back to build the thing.

## Beginning and ending

`captains_log_begin` returns a **stardate** (`20260813.8` — the day plus which tenth of it)
and an opening line. Say it back: *"Captain's log, stardate 20260813.8. Dave's inventory
app — first design pass."* That is the confirmation that you are recording.

Tag it so it can be found later:
- **`stardate`** — the general daily journal. Whatever happened, whatever's on their mind.
- **`project`** — a project being designed or discussed. `begin` returns
  `possible_duplicates`; if one of them is plainly the same project, say so and ask whether
  to continue it (`continue_from: <stardate>`) rather than starting a second log about it.
- Plus whatever names the subject: `roblox`, `instar`, `cenora`.

`captains_log_end` takes a `closing` — a few sentences on what the conversation amounted to
and where it leaves things. Then tell the owner the truth about what happens next:

> This is by proposal only. It's waiting for your approval, and the contents expire in 48
> hours if you don't approve it.

Say that plainly, every time. Do not promise you will remember something you might not.

## Only one log at a time

`begin` while a log is open returns the open one instead of starting a second — keep
appending to it, or close it first. If the conversation genuinely changes subject, close
the log and open a new one.

A log left open goes **abandoned** after 12 hours: closed and compiled from whatever it
has, and still sent for review. Nothing is thrown away because a connection dropped. But an
abandoned log has no closing summary and reads like it — so close your logs.

## Reading them back

`captains_log_search` (by text, `tags`, or a `stardate` prefix like `20260813`) returns
headlines; `captains_log_read` returns one in full. When the owner picks a logged
conversation back up: **read the log first, then talk.** Its open questions are where the
conversation should resume.

Only **approved** logs are searchable and readable. If a search comes back empty, that means
no approved log matched — not that the conversation never happened. Say that, rather than
reconstructing from imagination.

## Rules

- Open a log only when asked; close it when asked
- Summaries, never transcript; one idea per entry; always a `why`
- Say the stardate when the log opens and the expiry warning when it closes
- Never claim something is logged that you did not append
- Never describe the contents of a log that is not approved
- If the log skill is unavailable, say so — do not pretend to be recording
