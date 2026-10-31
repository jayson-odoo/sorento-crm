# CARD v2: The side panel runs the chatbot's brain

Status: v2 filed 31 Oct 2026, waiting on the owner's Q1-Q3. No product code yet. Replaces sections (b) and (d) of
`CARD-agentic-unify-31oct.md`; its section (a), the console's one thread, stands.

Owner, 31 Oct ~14:55, on Q1: "hmm I need the thinking and brain process to be same as chatbot, simple as that".
Also: Q2 (a) any staff with the rollout permission, as themselves. Q3 (a) fix the permission and company leak now, whole
panel. Q4 (a) new permission by role. Q5 (a) agent reads recent bot replies, thread survives reload.

Paths: `S` = `sorento_crm_backend/app/services`, `CHAT` = `S/chatbot`, `B` = `AIAssistantBubble.tsx`,
`AS` = `S/ai_assistant_service.py`.

## In short

**One brain, two surfaces.** A panel message goes through the same Jev, parser, lanes and agent as a WhatsApp message, as a
staff member with no WhatsApp contact. Nothing goes out on WhatsApp. Data changes only through the agent's Confirm card.
Questions the lanes cannot answer today become agent tools, so WhatsApp staff gain them too.

**This is much bigger than v1.** The brain knows only contacts, and it covers less than the panel does today (section 4).
Staff without the rollout permission stay on today's panel until the new path has caught up.

## 1. How a staff member enters a brain built for contacts

Recommend a **staff principal**, not a fake contact. All figures are from reading the code; the seam count is not compile-checked.

| | Staff principal | Internal contact row per user |
| --- | --- | --- |
| Code change | About 12 places, gathered behind one principal object | No engine change, if every row below is met |
| Needs | Nothing new in the contact tables | Fake unique phone (`models/access.py:268`), default workspace (`S/field_access.py:256`), office type and tier, company rows, AI switch on |
| Staff who already have a contact | Work | A user can link to one contact only (`models/user.py:144-147`), so linked lanes refuse them |
| Active company | Yes, one (`S/company_scope_resolver.py:189-218`) | No: a fixed set per row (`S/contact_access_type_service.py:379-396`) |
| Their permissions | Read from the user | Would have to be copied onto the contact and kept in sync |
| Visible to users | No | Shows in contact lists, counts, bulk toggles, company pages and the idea sweep (`api/v1/system/respond_contacts.py:51-150`, `S/ideation_turn_service.py:472-473`) |

What the brain asks of a contact today, and the staff answer:

| Brain asks | Today, from the contact | Staff principal |
| --- | --- | --- |
| May AI answer? | `CHAT/engine.py:3500` | Yes: the rollout permission already passed |
| Which companies? | `CHAT/engine.py:3477` | The user's active company |
| Which brands? | `CHAT/engine.py:3479` | All (`S/contact_brand_scope.py:101-102`), as staff screens show |
| Tier and profile | `CHAT/turn_runtime.py:455` | Office, built from the user |
| Which fields and tools? | `CHAT/engine.py:4592`, `S/mcp_access_service.py:77-80` | From the user's permissions |
| Whose customers? | `CHAT/lanes/business/services.py:703-711` | Staff |
| Session and memory | Row column, one thread per contact (`models/access.py:279`) | Per panel thread, via the console's existing per-run route (`CHAT/engine.py:4213-4218, 8609`) |
| MCP calls | Contact + workspace (`CHAT/lanes/business/services.py:287-289`) | Staff identity from your Q3 fix |

**Key change from v1:** one key per panel thread (`panel-<conversation id>`), not one per user. New chat then really starts
clean with no new column, and the daily cap counts across all of a user's threads. No colon in the key: the outbound
check splits on ":" and lets an unknown id through (`S/respond_identifier.py:62-63`, `S/respond_outbound_service.py:42-46`).
A test pins that a panel key can never be sent to.

**Permission gap to close:** the chat brain reads no user permission anywhere (grep: only `agent/` does). Your Q3 fix covers
MCP calls. Reads inside the process (stock, promotions, resolver) need a check at the principal. That list is not yet counted.

## 2. Side effects: same thinking, no accidental actions

A panel turn runs on the console's test path, which is built for zero writes outside `chatbot.turns`
(`CHAT/contracts.py:864-872`) and returns its session instead of saving it (`CHAT/engine.py:8609`). `run_turn` only returns;
its callers do the sending (`CHAT/inbox_queue.py:716-745`). The panel never executes the returned actions.

Why not a live turn: about 20 switches key on it (ordering, phone gate, stock asks, salesman job, escalation draw), and the
evidence file warns against switching `is_test` off and assuming it behaves (`EVIDENCE-agentic-identity-29oct.md` line 13).

Two things must change on this path: usage must be logged (today test turns log none, `CHAT/usage.py:8-10`), and a reply must
never claim an action that did not happen. A test-path escalation returns a preview of what it would do
(`CHAT/lanes/escalation.py:637-645`), which is a false statement on a real surface. See Q1.

## 3. A live risk found in the console (exists today, separate from this work)

Every console chat turn turns on `system_settings.chatbot_business_lane_enabled` and `chatbot_completed_lanes` globally,
commits, and restores them afterwards (`CHAT/console_service.py:257-289`). Live WhatsApp turns read those per turn
(`CHAT/engine.py:3525, 11044`). So on any install where they are not already all on, a console turn changes live customer
routing while it runs, and two overlapping console turns can restore the wrong values and leave them on. Production values: UNVERIFIED.
The panel cannot use this. I replace it with a per-turn override, which removes the flip from the console too.

## 4. Panel features ported into the brain

| Panel feature | In the brain today? | Where it goes |
| --- | --- | --- |
| Current page and record | No slot | New optional parser input (`CHAT/turn/context.py:222`), agent prompt (`CHAT/agent/loop.py:696-701`), Jev's state (`CHAT/router.py:196-225`). Absent means not one byte changes on WhatsApp (precedent `context.py:265-268`, proved by `tests/chatbot/test_parser_user_block_parity.py`). **You publish the parser rule** (`parser_template.py:25`) |
| "this complaint" | No: panel record kinds and brain kinds do not overlap (`S/record_context_service.py:42-47`, `CHAT/turn/policy_rows.py:31-40`) | Agent tools, given the page's record |
| How-to and guides | No (`user_guides_read` has no caller, `CHAT/contracts.py:60,88,171`) | Agent tool, from AGENTIC-KNOWLEDGE #2036. Panel keeps its link clean-up (`AS:3330-3500`) |
| Complaints, SLA tracking, projects, order analytics, find | No | Agent read tools (Q2) |
| Complaint close, order cancel, IT ticket | No, and left out of lanes on purpose (`CHAT/lanes/business/fetch.py:1456-1460`) | Agent write tools with Confirm (Q2) |
| PR decide, opportunity | Yes (`CHAT/agent/writes.py:724, 1521`) | Reuse |
| Capability answer | No | Agent tool |
| Ideas | Yes, needs a contact (`CHAT/lanes/ideate.py:84`) | Keep the /ideas link until AGENTIC-IDEATE moves ideas to the agent |
| Clarify chips | Yes, different shape (`CHAT/console_service.py:331`) | Mapped to the panel's chips (`B:732-752`) |
| Thread list, search, deep links | No | Panel's list stays; replies saved as panel messages |
| Usage, trace, wishlist | Usage and trace yes; wishlist no | Panel feature names (analytics counts `chatbot%`); wishlist stays keyed on panel messages (`S/ai_wishlist_service.py:27`) |
| Wording that assumes WhatsApp | `ai_prompt_registry.py:1078, 1091`, ideate prompts, `CHAT/turn/refer.py` | Edited, **you publish** |

The AI Assistant settings' provider and model stop applying on the new path; it uses the parser label and the agent settings.

## 5. Same three exchanges

Exact messages: **[dev]**, still owed by crew. "Today" is unchanged from v1 except for your Q3 fix.

| Staff asks | With one brain |
| --- | --- |
| **Stock** | Jev says chat, parser and stock lane answer as they would an office contact on WhatsApp, for the active company only |
| **Sales report** | Agent runs `crm_report_ask` as this user, with steps. That route reads brand and hidden fields from a contact (`api/v1/order_management/report_ask.py:287-295, 450, 463`), so it needs a staff branch. Size UNVERIFIED |
| **A write** | Agent proposes, card shows before and after, Confirm, then countdown and Undo where the action has them. Same as v1 |

## 6. Order

My reading of your Q3 answer: the leak fix is **not** behind the rollout permission, so it reaches every panel user at the next
release you approve. Some staff will see "no access" where they get an answer today.

1. **PR 1, this lane:** leak fix, console one thread, console flip removed.
2. **PR 2:** staff principal, page context, panel cards, rollout permission granted to nobody.
3. **PR 3:** the ported agent tools.
4. **Pilot, then default:** a labelled set of real panel questions, run through both today's panel and the new path. Default only
   when nothing is lost. Then `respond()` retires.

Three PRs is an exception to one lane, one PR: crew's call. A single PR this size is too big to review or hand-test well.

## Questions

**Q1. On the panel, may the chat lanes change data themselves?**
(a) No: anything that changes data goes through the agent with Confirm. Escalating to a person is not offered in the panel (it has
no such feature today). (b) Yes, lanes write as on WhatsApp.
**Recommend (a):** one write path, always confirmed. (b) means auditing about 20 live switches, and a panel user could trigger real
SLA rows and assignee draws with nothing delivered (`CHAT/lanes/escalation.py:1608`).

**Q2. Staff would lose answers on complaints, SLA, projects and order analytics, and three write actions. How do we close that?**
(a) Add them as agent tools before the pilot. (b) Pilot with the gap and port what people ask for. (c) New chat lanes, one per domain.
**Recommend (a):** your 30 Oct principle of general tools over hard-coded flows, and WhatsApp staff gain them too. (c) needs parser
domains and a prompt gate each. Depends on Jev sending these to the agent; AGENTIC-IDEATE's criteria-from-tools work helps.

**Q3. How should panel replies look?**
(a) Same as WhatsApp, using the existing `components/chatbot/WhatsAppText.tsx` and `TurnAttachments.tsx`; files then show in the panel,
tables go away (`B:661-663`). (b) Convert to markdown to keep tables.
**Recommend (a):** you asked for the same brain, and it needs no conversion layer. The mock shows it, so you can judge there.
