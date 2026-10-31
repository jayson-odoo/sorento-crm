# CARD: One conversation in the console, and the same routing in the AI side panel

Status: v1 filed 31 Oct 2026, waiting on the owner's answers to Q1-Q5. No product code yet.
Track: full pipeline, size L (auth surface, one additive column, two screens).
Plan: `PLAN-agentic-unify-31oct.md`.

Owner, 31 Oct ~13:20: "our chatbot console can just combine the bot and agent type to one now, because
now we got Jev to decide already, so at least from the chatbot console I can see is it using chat or
agent. And I want to unify this to our AI assistant side panel, so those that use the AI side panel can
enjoy this benefit also."

Data: every **[dev]** slot is filled from `agentic-unify-dev-data.sql`, run by crew, and delivered in the
crew report only. This repo is public; no real message or person is committed here.

Paths: `S` = `sorento_crm_backend/app/services/ai_assistant_service.py`. `CHAT` =
`sorento_crm_backend/app/services/chatbot`. `CON` =
`sorento_crm_frontend/app/(protected)/system-management/chatbot-console`. `B` =
`sorento_crm_frontend/app/components/common/AIAssistantBubble.tsx`.

## The short version

- **Console:** yes, simple. Bot and Agent tabs become one thread. Nearly all of it is existing pieces moved.
- **Side panel:** Jev can decide for the panel too, but one thing in the brief does not hold. The WhatsApp
  bot lanes cannot run as a logged-in staff user, because they need a contact (`CHAT/contracts.py:857-861`).
  So I recommend Jev chooses between **the panel's own pipeline** (chat) and **the shared agent** (agent).
- **A finding you should know about:** panel reads today are not limited to the staff member's permissions
  or company. Any staff member with the panel can read every company's data through it (`S:355-358`,
  `S:2718-2719`, `company_scope_resolver.py:244-248`). Q3 is about fixing this.

## (a) Console: one conversation view

Today: two tabs (`CON/components/ChatbotConsoleTabs.tsx:9-20`) with separate threads. Below, bare
`useChatbotConsole.ts` and `useAgentConsole.ts` are under `CON/hooks/`, `AgentConsole.tsx` under `CON/components/`. A turn the router
already sends to the agent shows as text and a pill on the Bot tab; its steps and write cards show only on
the Agent tab (`CON/hooks/useChatbotConsole.ts:94-110`).

Proposed: one thread, no tabs.

| Piece | Behaviour | Reuses |
| --- | --- | --- |
| Pill on every reply | Chat or Agent; opens to reason, score, model, time | `CON/components/RoutePill.tsx:25-58` |
| Steps + reasoning | Inside the bubble when the turn went to the agent | `StepsDisclosure`, `ReasoningItem`, `ReplyMeta` (`CON/components/AgentConsole.tsx:91-215`), moved out so both can import them |
| Write cards | Confirm, Cancel, countdown, Undo, before/after, in the thread | `ProposalActions`, `ActionsBlock`, `WaitingStep`, `ActionOutcome` (`AgentConsole.tsx:218-400`), `TakeoverCountdown` |
| Composer + bubbles | Attachments, voice, paste, reply-to, copy, retry, trace link all stay | `CON/components/ChatbotConsole.tsx:65-178, 543-706` |
| Force agent | **New:** an "Agent" toggle in the composer. Applies to the next message only, then switches off. Off when an attachment is present (media always goes to the bot) | The only new control |

Decisions already made (say if you disagree):

- The forced turn goes through `/console/turn` with a new `force_agent` field, so it gets the same reply shape
  and a pill reading "Forced". `/agent/turn` and the Agent tab are removed. Forced turns keep today's behaviour:
  not blocked by the daily cap, but counted (`CHAT/router.py:79-81, 160-170`; `api/v1/system/chatbot.py:712-744`).
- One "New conversation" button resets both sides. Today Reset leaves the agent's thread alone, and New
  conversation leaves the bot's alone (`useChatbotConsole.ts:191-196`, `useAgentConsole.ts:161-169`).
- A contact without the agent switched on still gets chat; the pill says why. No error banner, which is today's
  Agent tab behaviour (`useAgentConsole.ts:78-79`).

## (b) Side panel

### What it does today

`POST /system/ai-assistant/chat` (`api/v1/system/ai_assistant.py:303`) runs `respond()` (`S:900-1262`): one
parser call, shortcuts for capability, ideate and clarify, then record context, then its own tool loop (6 rounds,
3 calls, `S:2568-2569`) using the AI Assistant settings' provider and model. It already asks Confirm or Cancel
before a write (`S:2782-2801`, `B:756-781`). It waits for the whole answer, no streaming (`B:805-818`).

### How it would work

```
POST /system/ai-assistant/chat        same route, same gate, identity from the login session
  no rollout permission (Q4)     ->  respond()              exactly today
  Jev says chat, or low score    ->  respond()              exactly today
  Jev says agent, or a write is
    waiting for your Confirm     ->  shared agent loop, as this staff user
```

- **Identity (Q2):** thread key `staff:<user_id>` in the existing `contact_respond_id` columns. They are plain
  text with no foreign key (`models/chatbot_turn.py:84`, `models/chatbot_agent.py:33,62`), so the key needs no schema
  change, and the daily cap, one-turn-at-a-time lock and pending action then work per user with no new code. The user's own
  permissions decide tools (`user_may_use`, `CHAT/agent/tools.py:285-289`). Contact-only limits (grants, stock
  switch, brand scope, `tools.py:304-310`) do not apply; a staff member sees what their screens allow. The console's
  contact lookup does not recognise a `staff:` key, so it is refused there by default (`CHAT/agent/access.py:66-67`).
- **Write cards:** the same card components, in the panel. New panel routes for confirm, cancel and withdraw,
  gated by `system.ai_assistant_chat.use`, with the user taken from the session. The console routes are not reused:
  they need `system.chat_history.view`, which is customer PII (`rbac/permission_registry.py:405`), and trust a contact
  id sent by the client (`api/v1/system/chatbot.py:771`).
- **Thread:** the panel's list stays the only list staff see (search, deep links from tickets, `B:359, 385-429, 580`).
  Each panel thread maps to one agent conversation through one new nullable column, so going back to an old thread
  does not mix memory.
- **Who sees what:** write cards for everyone. Pill and steps only for those who can already see "View trace"
  (`system.ai_assistant_settings.view`, `B:84`); other staff just get the answer.

### Panel features

| Feature | Chat side | Agent side |
| --- | --- | --- |
| Current page and record context (`S:2404-2444`) | Unchanged | **Port:** same block added to the agent's system message |
| Guide answers, button deep links | Unchanged | Not ported first; how-to questions should route to chat. Re-check in the panel eval |
| Capability, ideate redirect, clarify chips | Unchanged | Not needed |
| Ticket create with source stamp (`S:2726-2740`) | Unchanged | Not ported first |
| Thread list, search, deep links | Unchanged | Agent replies are stored as panel messages, so they work too |
| Usage ledger | Unchanged | Separate panel feature names: analytics counts `feature LIKE 'chatbot%'` (`analytics_connector/views.py` ~205), so panel turns must not join them |
| View trace link | Unchanged | Steps shown inline instead |
| Attachments, voice | None today | None |

Nothing is lost on the chat side. Until the panel is default, staff can see two kinds of write card.

### Cost and latency

- Jev adds about 0.4 s at most to every panel turn (p95 389 ms) and costs about USD 0.03 per 1,000 messages
  (`PLAN-agentic-p2-route-30oct.md:134-135`, held-out n=120).
- An agent turn can run up to 8 rounds or 45 s (`CHAT/agent/loop.py:68-74`). The panel shows "Thinking..." meanwhile.
  It uses the agent's model (`gemini-3.5-flash`, `loop.py:47-51`), not the AI Assistant settings.
- Caps per user: the existing daily cap (default 50, `models/user.py:664`) counts per `staff:<user_id>`. Over the
  cap goes to chat. Per-user overrides wait until someone needs one. Actual panel and agent latency and tokens: **[dev]**.
- Router accuracy is measured on WhatsApp staff messages only. Panel text differs ("what is on this page"), so a
  labelled panel set is the gate before default. Low confidence goes to today's panel, which keeps the risk small.

### Document knowledge tool (AGENTIC-KNOWLEDGE, #2036)

Plan only, not on main. Its registry entry reaches the panel's agent side automatically; the chat side gets it from
the MCP list. Its plan needs `resource.attachments.view` for staff, and the endpoint cannot see the staff member
through MCP today (`S:358`: logged only). Q3(a) fixes that too.

## (c) Rollout

1. **One PR**, console merged and panel code behind the rollout permission (Q4), granted to nobody at merge.
2. **Console** live at the next release you approve.
3. **Panel pilot:** your own role first, then a few staff. Watch the pill, cost and refusals.
4. **Panel default:** only after the labelled panel set passes the same bars you set for WhatsApp. Then grant to all.

Touches the same code as open lanes: AGENTIC-IDEATE (router criteria), AGENTIC-KNOWLEDGE (#2036, registry),
NO-OPENAI (#2035, AI settings). Whichever merges second merges main first.

## (d) Three real panel exchanges

Exact messages and figures: **[dev]**, in the crew report. What changes:

| Staff asks | Today | With this |
| --- | --- | --- |
| **Stock** (a product's balance) | Chat loop calls MCP stock with blank contact: every company, no check of this person's permission (`S:2718-2719`) | Jev likely says chat, same answer, narrowed under Q3(a). If agent: `crm_inventory_stock_balance_list` after `inventory.stock.view` |
| **Sales report** (top products or customers for a period) | Cannot use the report engine: it refuses without a contact (`order_management/report_ask.py:287-295`), so the model pieces it together or fails (UNVERIFIED live) | Agent runs `crm_report_ask` as this user, with steps. **Needs work:** that route reads brand scope and hidden fields from the contact (`report_ask.py:450, 463`), so it needs a staff branch; size UNVERIFIED |
| **A write** (update a customer ask, or decide a purchase request) | Confirm or Cancel, then runs at once; no grace or Undo. Only tools in a fixed list check the permission (`S:1810-1830`) | Agent proposes, card shows before and after, Confirm, then countdown and Undo where the action has grace (`CHAT/agent/writes.py:1482-1494`). Permission re-checked per step at Confirm (`CHAT/agent/actions.py:145-164`) |

Limit: the agent has 23 tools: 11 reads, 6 in-process reads, 6 writes (`CHAT/agent/tools.py:61-75`, `CHAT/agent/writes.py:273, 368`). The panel's MCP list is
wider (exact gap not yet compared). A question Jev sends to the agent that needs a missing tool gets "I can't" rather
than today's answer. The plan compares the two lists before pilot.

## Architecture

- **Layer:** turn routing and identity, not prompts.
- **Shared mechanism:** one router and one agent loop, called by console and panel; one narrow-only staff identity at
  the API-key check (Q3).
- **Also fixes:** panel all-company reads, panel per-person permission on reads, knowledge tool seeing the staff
  member, report engine for staff.
- **Removes:** the Agent tab, `/agent/turn`, two Reset buttons. Later, after default: the panel's second write path.

## Questions

**Q1. What runs on the panel's chat side?**
(a) The panel's own pipeline, unchanged. (b) The WhatsApp bot lanes through the staff member's linked contact: only
linked staff qualify (**[dev]** count), loses page context and guides, and runs dry-run (`CHAT/console_service.py:156-168, 225`).
(c) No router; every panel turn goes to the agent.
**Recommend (a):** the only one that keeps every panel feature and works for every staff member.

**Q2. Who can use the agent from the panel?**
(a) Any staff member with the rollout permission, under `staff:<user_id>`, no contact needed. (b) Only staff with a
linked contact and both contact switches on (`CHAT/agent/access.py:50-80`). Cheaper, no new identity, but they get the
contact's view instead of their own, and only **[dev]** of the panel's users qualify today.
**Recommend (a):** it matches "their permissions" and caps per user.

**Q3. Panel reads ignore the person's permission and company today. Fix now?**
(a) Now, for the whole panel, behind the rollout permission: the API-key check honours the staff member's identity, can
only narrow access, and applies their active company and permission to each read. (b) Agent side only; chat side stays
all-company until a later lane. (c) Leave it.
**Recommend (a):** one mechanism at `require_permission_with_api_key` (`dependencies.py:524`) and
`_resolve_api_key_scope`. Under (b), Jev's choice would change what a person may see. Catch: some staff will get
"no access" where they get an answer today, correct but visible; multi-company staff see only their active company.

**Q4. How do we roll the panel out?**
(a) New permission `system.ai_assistant_chat.agent`, granted by role in the existing Roles screen. (b) One on/off
setting for everybody, as first briefed.
**Recommend (a):** pilot by person or role with no new screen or column; default means granting it to all. (b) has no pilot.

**Q5. How much should one console thread remember?**
Today neither side sees the other's replies (`CHAT/agent/memory.py:69-79`, `CHAT/engine.py:4213-4218`); only Jev sees both.
(a) The agent also reads recent bot replies in the same thread; the bot stays as is; one merged read so thread and write
cards survive a reload. (b) Visit only: a reload clears the thread, write cards included. (c) Both sides read each other,
which changes the parser's input and needs a prompt gate.
**Recommend (a):** a follow-up after a bot reply works, and the bot's prompts and gates are untouched. A follow-up to the
agent that Jev sends to the bot would still lack context; the router's "who answered last" makes this rare (UNVERIFIED).

## Mock

The merged console and the panel's cards change screens, so a Lavish mock on a real case follows as its own `--ask`
(`documentation/mockups/agentic-unify/index.html`). No build before it is approved.
