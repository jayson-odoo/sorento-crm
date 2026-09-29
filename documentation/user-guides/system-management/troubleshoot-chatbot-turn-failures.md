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
field name. Hover a chip to see the raw field name if you need it for a bug report.

If you need the underlying technical payload for a step (for a bug report to engineering), open
**Technical details** at the bottom of the trace - it is the full record for every step, searchable
in place.

## Photos and voice notes in the thread

When a contact sends a photo or a voice note instead of typing, the incoming message in the
thread shows what the bot read or heard, right above the message text:

* A **photo** shows as a thumbnail. Click it to open it full-size in the same lightbox used
  everywhere else in the CRM.
* A **voice note** shows as an audio player, with the bot's transcript already printed in the
  message text below it.
* A photo also carries a small **Read N items** chip, counting how many codes or other details
  the bot picked out of it. The chip turns **amber** when the photo held more than the bot was
  allowed to take in one go (see [Chatbot - photos and voice
  notes](chatbot-media-intake.md)) - that's your signal the reply only acted on the first ones,
  not the whole photo.
* When a photo or voice note is refused or fails outright (not enabled for this number, over
  the monthly allowance, too many at once, unreadable), there is no thumbnail or player at
  all - just the bot's plain reply explaining why, the same reply the contact received.

Opening the Turn trace on one of these messages shows one extra step, **Read the photo** (or
**Heard the voice note** for a voice message), alongside the usual Received/Understood/etc.
steps - naming what was read or heard, and whether it was accepted, denied or failed. This step
does not appear at all on an ordinary text message.

## The full trace panel

For more than the raw payload, click the small tree icon at the end of the Turn line (its label
is **Open full trace**). This opens a panel titled **Turn #&lt;short id&gt;** with one collapsible
section per part of what the bot did, in plain words first and the raw record underneath each:

* **Stages** - the same step list as the collapsed timeline, in one place.
* **Parse** - what the bot's language model actually understood from the message: which prompt
  version and model answered, plus the reading it produced before and after clean-up.
* **Apply** - what the bot decided to do with that reading: anything it changed in what it
  remembers about this conversation (each change shown as *before -> after* with a one-line
  reason), any narrowing rule that fired, whether it had to work out which topic a word actually
  meant, and the plan it built for the rest of the turn. A collapsible line under this section
  shows the exact text sent to the language model, for an engineering bug report.
* **Memory** - the bot's three shelves of memory, before and after this turn: **Focus** (this
  conversation's current topic and detail, written by Apply), **Profile** (this contact's own
  settings - tier, language and so on, written by the [Contact chatbot
  card](../user-management/contact-chatbot-card.md) or the customer's own pick), and
  **Episodes** (an earlier closed topic in this same conversation, when the bot pulled one back
  in) - shown as a recall "hit" or "not triggered", with why.
* **Decay** - anything that aged out of memory automatically on this turn.
* **Open question** - the question the bot was waiting on an answer for, and how this message
  answered (or didn't answer) it.
* **Focus** - one line per rule that changed what the bot is currently tracking about this
  conversation (e.g. which product, which customer), and why it changed.
* **Tool** - the actual lookup the bot ran: which one, what it was asked, and what it returned.
* **Cross-domain** - when the first answer came back empty or thin, the extra related topics the
  bot checked next (its "ladder" - see [Chatbot Domains](chatbot-domains.md)), and whether each
  one found anything worth reporting.
* **Field reveals** - any normally-restricted detail that was on this answer, and whether this
  contact was allowed to see it.
* **Session** - what the conversation's memory gained or lost this turn, before and after.
* **Sent** - whether the reply actually went out, and how long that took.

A section that has nothing to show says so in one line (e.g. "No tool call recorded.") rather than
appearing empty or broken. Two sections - **Apply** and **Memory** - only fill in for turns run on
the current turn engine; an older turn shows "Not recorded on this turn" for those two instead.

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

## Settings that change what the bot answers itself

These are now on-screen settings rather than backend-only switches - see
**[Chatbot settings](../user-management/chatbot-settings.md)** for the Switches, Memory, Tier
order and Cross-domain ladder cards, and **[Chatbot Domains](chatbot-domains.md)** for which
topics the bot supports at all.

* **Which lanes the CRM finishes itself, versus handing to the WhatsApp automation team.** The
  turn engine now decides this for itself on every message - there is no more free-standing list
  of "lanes the CRM answers". **Business lane** and **Ordering**, on Chatbot settings' Switches
  card, are what is left: whether the bot answers ordinary business questions itself at all, and
  whether it finishes every kind of question end to end. Turning **Ordering** on is confirmed
  first, because any lane still switched off elsewhere then has nobody left to answer it.
* **Whether the bot is allowed to tell a customer their stock question is refused.** The **Stock
  denial lanes** switch on Chatbot settings. Off by default. While off, that kind of question is
  not reachable at all - the customer's message simply cannot land there. Turning it on without
  the reply already being reviewed risks the bot telling a customer "no" in the wrong words.
* **Which topics the bot always says it cannot help with.** No longer a typed list - each topic's
  own **Supported** switch on **[Chatbot Domains](chatbot-domains.md)** controls it now. Switching
  a domain off there means customers get no answer on that topic at all, from that point on.

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
* [Chatbot - "which products have X" (asking for a set)](chatbot-attribute-set-answers.md) - what
  a customer sees when they ask for a whole group of products at once, and the Lookup Sets an
  admin fills in to teach the bot new words for it.
* [Chatbot - "last purchase cost" answer](chatbot-last-purchase-cost.md) - the per-contact
  Field reveal that gates a cost answer, and rolling out its parser vocabulary via a Publish.
* [Chatbot - photos and voice notes](chatbot-media-intake.md) - what a contact sees when they
  send a photo or voice note, and why one might be refused.
* [Chatbot Domains](chatbot-domains.md) and [Entity kinds](chatbot-entity-kinds.md) - what a
  domain answers, how it narrows, and its ladder to other topics.
* [Chatbot settings](../user-management/chatbot-settings.md) - the Switches, Memory, Tier order
  and Cross-domain ladder cards.
* [Contact chatbot card](../user-management/contact-chatbot-card.md) - per-contact stock checks,
  recall, tier and language.
