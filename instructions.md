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
- **Every entry carries a `reason`** — what it settles, unblocks, or constrains. If you cannot
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
- Plus whatever names the subject: `roblox`, `instar`, `work`.

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

---

## On a chat surface, the log is a TOOL you open

"Open the captain's log" is a request to GO somewhere, not to be told what the log can
do. Open the workspace first — it gives the tool the screen and moves the conversation
to the side — and put everything else inside it.

```json
{"op":"workspace","id":"captains_log","title":"Captain's Log","state":"open"}
{"op":"upsert_block","region":"workspace_nav",
 "block":{"type":"button","id":"n_search","label":"Search","action":{"id":"search"}}}
{"op":"upsert_block","region":"workspace","block":{"type":"capability_set", "...": "..."}}
```

The rail (`workspace_nav`) holds the few things the log does and stays put while the
surface scrolls. The surface (`workspace`) holds what they are looking at.

### Every row they can see, they can press

A list of logs that cannot be clicked makes someone say the name of a thing already on
their screen. Give the results `select`, and every row becomes pressable:

```json
{"op":"upsert_block","region":"workspace",
 "block":{"type":"items","id":"log_hits","title":"Logs matching \"sonora\"",
   "select":{"id":"open_log"},
   "items":[{"id":"20261015.1","title":"Karyn bot for Sonora","state":"done",
             "meta":["stardate 20261015.1","15 entries","project · karyn · sonora"]}]}}
```

Pressing one sends you `action_id: "open_log"` with the row's id as `value`. Read that
log and replace the surface with its document — same `region:"workspace"`.

So the whole path, with no typing and no speaking:

| they press | you do |
|---|---|
| **Search** (capability or rail) | `captains_log_search` → an `items` block with `select` |
| **a log row** | `captains_log_read(stardate)` → a `document` in the workspace |
| **Close the log** | `captains_log_end` |

**Press the control you used.** Before you replace the surface, send
`{"op":"press","action":"search"}` so the thing they pressed visibly reacts, and so a
surface YOU changed on your own initiative still reads as an action rather than a glitch.

**A press is a claim, not an authority.** `open_log` carrying a stardate is a request to
read that log, checked exactly like a spoken one — it does not bypass the approval gate,
and an open log still refuses to be read.

## On a chat surface, the log is a DOCUMENT

When `user_context.surface == "chat"` the person is looking at a live page, and a log
is the clearest case there is of something that must not be narrated. `captains_log_read`
already hands you the structure — title, stardate, entry count, sections keyed by kind.
Retyping that as prose with asterisks produces a wall of punctuation, because the page
renders text literally, and it throws away the structure the tool did the work to build.

Put it in `region:"workspace"` when the tool is open, `region:"stream"` when it is not
— a document in the stream is a message that scrolls away, which is right for an answer
and wrong for something they are reading inside a tool.

```json
{"op":"upsert_block","region":"workspace",
 "block":{"type":"document","id":"log_<log_id>","title":"<title>",
   "meta":["stardate <stardate>","<entry_count> entries"],
   "sections":[{"heading":"Purpose","body":"<purpose>"},
               {"heading":"Decisions","items":["...","..."]},
               {"heading":"Risks","items":["..."]}]}}
```

One section per `kind`, in the order they matter. Use `body` for prose and `items` for
a list of entries — never a single blob with dashes in it.

### While a log is OPEN, show it filling up

`captains_log_read` only reads an APPROVED log — it will refuse an open one, and it is
right to: an unapproved log is a proposal, not a record.

For the log being dictated right now, use `captains_log_status`. Its `open.sections`
carries the entries so far in the same shape, because that log is the owner's own
words in this session being shown back to them.

An append is the interesting moment, so re-send the document with the new entry in
place. Same block id, so the page updates that document rather than stacking a second
copy, and the person watches their conversation become a record.

Do not re-send on every sentence. Re-send when an entry is actually appended.

### Controls, not instructions

Offer the next action as a button rather than telling them to say it:

```json
{"type":"button","id":"b_end","label":"Close the log",
 "action":{"id":"log_end","mode":"tap"}}
```

A press comes back to you tagged `[control:log_end]`, so you can tell it apart from
someone happening to say "close the log". Offer only what is actually available: no
close button when nothing is open, no append button on a log that is already closed.

### Put it down without losing it

A log the person is finished reading should be minimised, never cleared:

```json
{"op":"panel","target":"log_<log_id>","state":"minimized"}
```

It becomes a chip they can click — or say the name of — to bring back, and the chips
sit most-recent-first. **A log that is still recording keeps a live dot on its chip**,
which is the point: putting a recording log away must never hide that it is recording.
`clear` would destroy it and that is almost never what is wanted.
