# Chatbot Console - test the bot and use Agent mode

Use the Chatbot Console to try the WhatsApp bot on a real contact without sending anything to
WhatsApp, and to use **Agent mode**: an assistant that looks things up for a contact (stock,
incoming shipments, orders, sales) and, when you confirm, makes a small set of changes for them
(customer asks, opportunities, a contact's access, approving or rejecting a purchase request).

## Where to find it

Open **System Management > Chatbot Console** (`/system-management/chatbot-console`). Page header:
**Chatbot Console**. You need the **Chat History** view permission
(`system.chat_history.view`); without it the menu item is hidden and the page refuses to open.

The page has two tabs at the top: **Bot** and **Agent**. It opens on **Bot**.

## Before you start: turn Agent mode on for the contact

The agent only works for a contact that is allowed to use it. On the contact's page
(**Contact Details**, **Chatbot** card), switch on **Agent mode (auto)**. It is off by default.
Next to it, **Agent turns per day** caps how many agent answers that contact can get per day;
leave it empty to use the global value (shown as the placeholder).

The agent also needs:

* **AI replies** switched on for the contact.
* The contact linked to an **active user** (the agent acts as that user, see "Whose permissions
  apply" below).

If any of these is missing, the console tells you which one:

| Message | What to do |
|---|---|
| *This contact was not found.* | Pick the contact again. |
| *AI replies are off for this contact.* | Turn AI replies on for the contact. |
| *Agent mode is off for this contact (Contact Details > Chatbot).* | Switch on **Agent mode (auto)**. |
| *This contact has no linked active user.* | Link the contact to an active user. |
| *The agent is still working on another message for this contact.* | Wait for the earlier answer, then send again. |

## The Bot tab: the bot or the agent answers, automatically

On the **Bot** tab you type as if you were the contact on WhatsApp. For every message, the
system decides whether the normal bot or the agent should answer. You do not pick per message:
switching on **Agent mode (auto)** means the contact *may* be routed to the agent.

The decision is made by a classifier called **Jev**. Under each answer a small pill reads
**Agent** or **Chat** (who answered). Click it to see **Reason**, **Score**, **Model** and
**Time**. The reason is one of:

| Reason | Meaning |
|---|---|
| **Classified** | Jev was confident and picked this side. |
| **Low confidence** | Jev was not sure enough, so the bot answered. |
| **Open question** | The bot had just asked the contact something, so the bot handles the reply. |
| **Media** | A photo or voice note always goes to the bot. |
| **Daily cap** | The contact used up its agent answers for today, so the bot answered. |
| **Pending action** | The agent proposed a change and is waiting for a yes or no, so the agent answers. |
| **Router failed** | Jev did not answer in time (or is not set up), so the bot answered. |
| **Not eligible** | The contact is not allowed to use the agent. |

Once the agent is chosen it does not hand back to the bot. If it cannot answer you see *The agent
could not answer this message. Try again.*, or, while an earlier message is still running, *The
agent is busy with an earlier message for this contact. Try again in a moment.*

Only Chatbot Console turns are routed this way today. Real WhatsApp messages still go to the bot.

## The Agent tab: talk to the agent directly

1. Click the **Agent** tab.
2. In **Contact**, pick the contact (*Pick a contact...*).
3. Type in the box (*Ask about stock, orders or sales*) and press **Enter** (Shift+Enter adds a
   new line). While it works you see **Working...**.
4. Click **New conversation** to start fresh. This also clears what the agent remembers from the
   earlier messages.

Change proposals show **Confirm** and **Cancel** buttons only on the Agent tab. On the Bot tab a
proposal arrives as plain text; reply "yes" or "no" and the agent picks it up.

### What the agent can look up

**Sales report**, **Stock balance**, **Incoming stock by product**, **Incoming shipments**,
**Goods received**, **Last cost**, **Purchase orders placed**, **Last receipt**, **Orders by
product**, **Find names and codes**, **Find products**, **Customer asks**, **Opportunities**,
**Opportunity stages**, **Find contacts**, **Purchase requests** and **Recent changes**. Each one
is only offered when the linked user has the matching view permission (for example **Stock
balance** needs the stock view permission).

Figures in an answer that the agent cannot trace back to something it looked up are replaced with
*(not verified)*.

### What the agent can change (always after you confirm)

| Action | What it does | Permission the linked user needs |
|---|---|---|
| **Update customer ask** | Marks a customer ask done or open, and/or sets its note. | Customer asks: edit |
| **Create opportunity** / **Update opportunity** | Adds an opportunity or changes one. | Opportunities: add / edit |
| **Update contact access** | Switches a dealer contact between Business owner and Employee, turns their AI replies on or off, links or unlinks their customer accounts. Resigning a contact (AI replies off and accounts unlinked) can be undone. | Contacts: edit (or edit own) |
| **Decide purchase request** | Approves or rejects a purchase request or sponsorship form. A rejection needs a reason. The requester and the dealer contact are told. | Purchase requests: approve |
| **Undo purchase request action** | Withdraws a decision that is still waiting to apply, or undoes one that already applied (needs a reason; everyone involved is told). | Purchase requests: approve |

## Confirming a change

The agent never changes anything on its own. It first **proposes**: the reply lists the changes,
and under it are **Confirm change** (or **Confirm N changes**) and **Cancel**.

1. Read the list of changes.
2. Click **Confirm change** to apply, or **Cancel** to drop it. You can also answer "yes" or "no"
   in your next message.

Rules:

* A proposal expires after **10 minutes**. One confirmation covers at most 20 changes.
* You cannot confirm in the same message that asked for the change; the agent always waits for
  your next step.
* On confirm, every change is checked again (permission, the record has not changed since,
  company scope) and applied in order. It stops at the first failure.

The result shows a badge: **Done**, **Partly done**, **Not changed**, **Cancelled**, **Waiting**
or **Expired**, then who decided, each step, and every changed field as `Field: before -> after`.
This stays after a page reload.

If a proposal cannot be confirmed you see one of: *This proposal expired. Ask again to get a fresh
one.*, *A newer proposal replaced this one.*, *This proposal was already decided.*, *The record
changed since this was proposed.*, *The agent can no longer act for this contact.*, or *You do not
have permission for this change.*

### Approve or reject a purchase request: the countdown and Undo

A purchase request decision waits out the same grace window as the **Approve** / **Reject**
buttons on the request itself (set per form SLA stage; it is 0 seconds unless an admin set one).

* With a grace window, the result shows a draining countdown (`m:ss`, then **Finalizing…**) and
  an **Undo** button. Click **Undo** before it ends: *Withdrawn. Nothing was changed and nobody
  was told.*
* With no grace window, the decision applies at once. You can still ask the agent to undo it; it
  then needs a reason and tells everyone involved.
* Clicking **Undo** too late shows *That change already applied, so it can no longer be
  withdrawn.*

## Seeing how the agent worked it out

Under each agent reply:

* Chips: **N rounds**, one chip per tool it used (tool name and result), and, if it ran out of
  budget, **Stopped:** with the reason (rounds limit, time limit, token limit, or an error).
* **Steps** (click to open): the rounds, tokens used, and one plain line per lookup (what it
  read, how many rows, nothing found, refused, proposed).
* **Thinking (round N)** and **Thinking (final answer)**: the agent's own reasoning for that
  round, collapsed by default. It only appears when reasoning is switched on for the agent prompt.

If the agent hits a budget limit it still gives one final answer, saying what it did not get to
check ("I stopped at the ... limit before finishing, so I did not check: ...").

## Whose permissions apply

The agent acts **as the contact's linked user**, inside that user's company. It can only look up
or change what that user could.

To confirm a change, **you** (the person at the console) must also hold every permission that
change needs. Otherwise you see *You do not have permission for this change.*

Every confirmed change is real (it is not a rehearsal like a bot test turn) and is recorded in
the audit trail under the linked user, with you named as the person who confirmed it.

You can send up to 30 agent messages per 10 minutes; past that you see *Too many agent messages,
wait a few minutes.*

## Settings (admins)

* **User Management > Settings**, **Chatbot Media** tab (`/user-management/settings/chatbot-media`), card **Agent budgets**: **Tool rounds**, **Seconds per turn**,
  **Input tokens per turn**, **Compact history above (tokens)**, **Router minimum score**
  (0.5 to 0.95; below this Jev's choice is ignored and the bot answers) and **Agent turns per
  contact per day** (0 means no cap).
* **System Management > AI Assistant > Settings** (`/system-management/ai-assistant`): **TypeSafe (Jev) API key**. Without it every
  Bot-tab message goes to the bot (reason **Router failed**).

## See also

* [Contact chatbot card](../user-management/contact-chatbot-card.md)
* [Chatbot settings](../user-management/chatbot-settings.md)
* [Read a chatbot turn trace, and retry a failed one](troubleshoot-chatbot-turn-failures.md)
* [Project Sales Admin - Purchase request & sponsorship form lifecycle](../project-sales-admin/purchase-request-lifecycle-and-next-actions.md)
