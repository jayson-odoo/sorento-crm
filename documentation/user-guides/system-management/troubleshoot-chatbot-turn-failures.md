# Read a chatbot turn trace, and retry a failed one

Use this when a WhatsApp customer says the bot answered wrongly, didn't answer at all, or you
just want to see what the bot actually did for one message. Every incoming WhatsApp message the
bot looks at is a "turn", and every turn writes its own trace - a plain-language, step-by-step
record of what it understood, whether it was allowed to answer, what it looked up, and what it
sent back.

This is an admin flow under **System Management > Chat History**. There is no separate page for
it - the trace lives under each message inside the conversation thread.

## Where to find it

1. Open **[Chat History](/system-management/chat-history)**.
2. Click a row to open the thread drawer for that contact.
3. Under any **incoming** message, there is a **Turn** line. Click it to expand the trace.

## Reading the Turn line (before you expand it)

Even collapsed, the Turn line tells you the outcome in one glance:

* A status word - **Answered**, **Escalated**, **Asked to clarify**, **Asked for a quantity**,
  **Offered to escalate**, **Escalation declined**, **Refused**, or **Failed at &lt;stage&gt;**
  (e.g. "Failed at Understood"). A failed turn is shown in the destructive (red) tone so it stands
  out while scanning a long thread.
* The lane, in words, underneath (e.g. "Business query", "Escalation") - what kind of request the
  bot decided this was. Omitted when it would just repeat the status word, or when the turn failed
  before the bot got far enough to decide.
* **attempt N** - only shown once someone has retried this message; N counts how many times.
* **test** - this turn was a rehearsal, not a real customer conversation (see "Testing safely"
  below).
* The total time it took, and a short id (e.g. `#a1b2`) you can quote to engineering without
  handing over the full internal id.

## Reading the expanded trace

Expanding the Turn line shows the steps the bot actually ran, top to bottom: **Received,
Understood, Access, Routed, Looked up, Replied, Remembered, Sent**. Each step shows:

* a plain-language sentence saying what happened and why,
* a handful of key facts (e.g. which lane it routed to, what it looked up),
* how long that step took.

**A step that a lane simply never needed is left out entirely** - for example, a "please clarify"
reply never looks anything up, so there is no Looked up row and that is not a problem. That is
different from a step that a *failure* prevented from running: when a turn fails partway through,
everything after the failure point is collapsed into one grey **not reached** row naming the
skipped steps together (e.g. "Routed · Looked up · Replied · Remembered"), with "Memory was left
unchanged." underneath it - this tells you the rest of the turn was skipped on purpose, not that
something is missing from the record.

The **Remembered** step, when it ran, lists what changed in the bot's memory of this contact as
**kept**, **new**, or **cleared** chips - in words (e.g. "topic", "price tier"), not the internal
field name. Hover a chip to see the raw field name if you need it for a bug report. See "What the
bot remembers between messages" below for what these chips mean in practice.

If you need the underlying technical payload for a step (for a bug report to engineering), open
**Technical details** at the bottom of the trace - it is the full record for every step, searchable
in place. For a more readable version of the same detail - including exactly which memory rule
fired and why - click the small **Open full trace** icon beside the Turn line; it opens a drawer
titled **Turn #&lt;id&gt;** with a section for each step, including **Focus** and **Open question**
(see below).

## When a turn shows Failed

A failed turn's step shows the reason in one sentence, in place of the usual summary. Common
causes:

* **Failed at Understood** - the bot's language model could not make sense of the message, timed
  out, or errored. The customer already received today's standard "something went wrong" reply.
* **Failed at Handover** - the bot handed this message to the WhatsApp automation team's workflow
  to finish, and that workflow never reported back within its time limit. This usually means the
  automation side had an error or was being redeployed when the message came in. If you see
  several of these close together, it is a signal that something broke on the automation side
  around that time, not that any one customer's message was unusual.
* Any other **Failed at &lt;step&gt;** - read the sentence in that step; it names what went wrong.

**Nothing about this retries itself.** The bot never automatically tries a failed message again -
that is deliberate, so a customer is never answered twice for the same message. If a message
genuinely needs re-answering, a person has to press **Retry turn** on the failed step.

### Retry turn

* Pressing it re-sends the *original* WhatsApp message back into the bot's front door, exactly as
  if the customer had sent it again. It arrives back as a brand-new turn (with the attempt count
  bumped up); the failed row you retried from stays failed, as the record of what happened the
  first time.
* The button is greyed out, with a reason shown next to it, when:
  * the turn did not actually fail (nothing to retry),
  * a retry for this same turn is already on its way (wait for it to arrive as a new turn before
    asking again),
  * or this environment simply has no automation front door configured to retry into (this is
    normal on a development machine; it is not a bug).
* Retry needs a slightly wider permission than viewing the trace, so if you can see the trace but
  not the Retry button, that is expected for your role - ask an admin to retry it instead.

## Finding failed conversations quickly

On the **Chat History** list itself, open **Filters** and turn on **Failed turns only**. The list
then narrows to contacts who had at least one failed turn in the selected date range, and the
**Contact** column shows a badge naming the stage the *last* failure stopped at (e.g. "failed at
understood") plus a count if there was more than one.

Inside a thread, the drawer header has its own **Failed turns only** toggle (with a count badge)
that jumps you straight to the messages whose turn failed, without scrolling the whole
conversation.

## Testing safely

A turn marked **test** is a rehearsal: nothing is written to the contact's memory, no message is
sent to a real customer, and every action the bot *would* have taken is shown but flagged as a
preview rather than actually done. Turns opened from an internal chat console, a replay, or a
deliberate dry run are marked this way automatically - you do not need to remember to flag
anything yourself, and you can safely open, expand, and even attempt to retry a test turn without
any risk of a real WhatsApp message going out.

## What the bot remembers between messages

Between one WhatsApp message and the next, the bot keeps two things about a contact: what it is
currently focused on, and at most one question it is waiting for an answer to.

**What it stays focused on.** The bot keeps what the dealer asked about - which products, which
customer, a date range, which domains (stock, incoming, purchase orders, and so on) - across
messages, so a dealer does not have to repeat themselves every turn. A focus is replaced only
when the dealer names a new one (a different product code, a different domain word), says
something like "another one", or the conversation is closed in Respond.io. **Nothing ages by turn
count** - there is no setting that clears a focus after N messages, so a product asked about ten
messages ago is still the one a bare follow-up question is answered against, as long as nothing
above has reset it.

**At most one open question.** When the bot needs one more thing before it can answer - which of
several matching products, which customer, which price tier, which team to escalate to, which
company, which staff member - it asks exactly one question and remembers that it is waiting.
That question stays open until the dealer answers it, a newer question replaces it, or the dealer
asks something new instead. A numbered list of options never repeats a number within the same
message, so a reply like "2" always resolves to the same option the dealer was just shown. If the
bot offers to escalate and more than one team could take it, a plain "yes" does not pick one for
you - the bot asks which team, with a button per team.

Where to see this at work: the **Decay** panel in a turn's full trace (see "Reading the expanded
trace" above) names which slot was cleared this turn and why; the **Focus** panel lists what
focus rule fired and what it changed; the **Open question** panel shows what was asked, how the
dealer's reply was read, and what happened next. Each panel shows a plain sentence (e.g. "No focus
rule fired this turn.") when nothing happened on that turn - that is normal, not a gap in the
record.

## Watching a new parser version before you trust it (the shadow window)

Before an owner makes a new version of the bot's language-understanding step (the "parser") the
live one, they can run it in a **shadow window**: the candidate version runs beside the live one
on every real WhatsApp turn, but only *after* the customer has already been sent their reply. It
writes its own record of what it understood; it never answers a customer, never changes what the
bot remembers about a contact, and never sends anything. This lets the owner watch, over real
traffic, whether the candidate version agrees with the live one before switching over.

**Turning it on:** under **[User Management → Settings → Chatbot](/user-management/settings/chatbot)**,
set **Parser shadow version** to the version to trial (shown as e.g. `v18 · full · production`,
stored as `chatbot_semantic_parser@18`). It is a clearable select - set it back to **Off** to stop
the shadow runs. Leaving it unset means nothing extra runs at all.

**Watching it in Chat History:** on the **[Chat History](/system-management/chat-history)** list,
the **Shadow** button swaps the usual message grid for a list of shadow turns across every
contact, with columns **Time**, **Contact**, **Message**, **Live** (what the real turn decided),
**Shadow** (what the candidate version decided for the same message), and **Drift** - a badge
reading **agrees** when the two match, or naming which parts disagree (e.g. "branch, domains")
when they don't. Above the grid, a summary line gives the count of shadow turns in the selected
range plus how often the two agreed (**branch parity**, **asks parity**), reading "not measured"
rather than 0% when nothing could be compared yet. The grid itself shows at most the newest 200
shadow turns in the range; the summary line still describes the whole range even when there are
more than that.

Shadow turns never show up in the normal Chat History message list, are never counted as a failed
turn, and there is no **Retry turn** for one - nothing was sent to a customer, so there is nothing
to resend. Clicking a shadow row opens the same turn drawer as any other turn, but for the real,
live turn the customer actually received (since that is the one that matters) - its **Parse**
section shows the live parse and the shadow parse side by side.

**Watching it inside one conversation:** open a thread and its own **Shadow** toggle (beside
**Failed turns only**) compares that conversation's turns one by one instead - each Turn line
gets a small badge reading **shadow agrees**, **shadow differs: &lt;what&gt;** (e.g. "branch,
domains"), or "no shadow parse" when no shadow row exists yet for that message, and the same
summary line appears above the transcript, scoped to that one conversation.

Promoting the candidate version once the owner is satisfied is the same **Publish** action
described under "Editing what the bot says" below.

## Settings that change what the bot answers itself

These are backend switches, not something you will find as a toggle on a settings page today -
ask your engineering / integrations contact to change them, and check with them before assuming a
setting is the cause of unexpected behaviour.

* **Which lanes the CRM finishes itself, versus handing to the WhatsApp automation team.** Every
  kind of request the bot can answer (a "lane" - e.g. an access refusal, a promotion question, an
  escalation) ships turned **off**: the CRM still decides what kind of request it is and records
  the turn, but the actual reply still comes from the WhatsApp automation side, exactly as before.
  Engineering turns a lane on for the CRM to answer only after watching it run safely for a while.
  **Lanes are turned on one at a time, in the order engineering built and tested them** - not
  whichever order seems useful day to day. Naming a lane that hasn't shipped yet, or misspelling
  one, does nothing (the bot keeps handing off, safely) - it never sends a message it wasn't ready
  for. If a customer-facing reply looks wrong right after a lane was turned on, tell engineering
  which lane and when, rather than trying to turn it off yourself.
* **Whether the bot is allowed to tell a customer their stock question is refused.** Off by
  default. While off, that kind of question is not reachable at all - the customer's message
  simply cannot land there. Turning it on without the reply already being reviewed risks the bot
  telling a customer "no" in the wrong words.
* **Which topics the bot always says it cannot help with** (today: goods-receiving and stock
  allocation questions). Of the three switches here, this is the one that has actually been
  changed before - it is a plain list of topic names, not a whole configuration screen. Removing a
  topic from the list without the bot actually being able to answer it means the customer gets no
  "I can't help with that" reply at all and the message goes unanswered from their point of view.

## Editing what the bot says

The bot's canned replies (the fixed sentences it sends for things like an access refusal, an
escalation offer, or "sorry, I can't help with that") and its own language-understanding prompt are
**not** hard-coded - they are editable under **[Prompts](/system-management/ai-assistant/prompts)**
(System Management > AI Assistant > Prompts), the same versioned prompt registry the AI assistant
itself uses. An owner can write a new version, then **Publish** it to make it the live one, with no
deploy. Every published version stays on record, so a bad edit is undone by publishing the
previous version again, not by asking engineering to revert code.

## See also

* [System Management - Data reference for admins](data-analysis.md) - full field/status reference
  for the `chatbot.turns` table.
* [Troubleshoot a failed notification (email or WhatsApp)](troubleshoot-failed-notifications.md) -
  for a WhatsApp send that failed for reasons unrelated to the bot (e.g. a bad workspace key), not
  the bot's own decision-making.
