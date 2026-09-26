# UAC - Chatbot memory: contact profile, episodes, turn context under a token budget

Plan: `PLAN-chatbot-memory-26sep.md`. Issue #1282. Numbering: AC-MEM001 to AC-MEM099, grouped
by slice. Tags: `[BE]` backend, `[FE]` frontend, `[E2E]` recorded agent-browser run, `[T]`
test evidence named in the line. Every criterion names its evidence.

Status: DRAFT 26 Sep 2026. **Written to the recommendations** of the plan's "Grill questions
for the owner" (Q1 to Q14). Where the owner answers differently, the ACs tagged with that
question (`(Qn)`) are rewritten before any code.

Terms: "contact" = a Respond.io contact through `/api/v1/external/chat/turn`; "dealer" = the
person behind it; "staff" = a CRM user with `user_management.contacts.view` (read) or
`.edit` (write); "operator" = a CRM user with `system.chat_history.view`; "episode" = one
`conversation_frames` row; "live episode" = the contact's turns since the last episode's
`closed_at`; "est. tokens" = `ceil(utf8_bytes / 3)`.

## Journey

### A. Mr Tan, a dealer on WhatsApp (the owner's "human conversation")

The system already knows, before he types: who he is (contact, linked customer Chin Chun
Trading, segment dealer, salesperson Aina), what he usually asks about (products SRTWB1455 and
M486-75-BL, site Kuching, tallied from his closed episodes), what he told the bot about
himself (role purchaser), what he asked in his last three conversations (one line each), and
what he said a minute ago in this one. He is never asked for any of it again.

1. Thursday 10:02. "stock SRTWB1455". Normal stock answer.
2. 10:03. "and in kuching?". The parser sees his earlier message in this conversation and
   carries the product; Kuching stock.
3. 10:05. "outstanding DO for chin chun". Topic switch: the stock conversation is closed as an
   episode with the summary "Thu 25 Sep, 2 turns: stock SRTWB1455 (answered)." The DO report
   renders.
4. Friday 09:10 (a gap of more than 30 minutes). "morning boss". The Thursday DO conversation
   is closed at intake; the bot greets him by name, names what he looked at last time and
   offers to re-run it.
5. "any update on that DO?". Resolved from yesterday's episode; the report re-runs with
   today's data, opening with one line naming what was carried.
6. "what did I ask you last week?". A numbered list of his recent conversations, no old
   figures, "reply with a number and I'll run it again".
7. "can give 10% discount for SO-2409-0112?". The bot cannot approve it; it says so in one
   human sentence and offers to pass it to Aina with the SO attached (yes / no).
8. "I'm the new purchaser, taking over from Mr Lim". Noted as a fact; nothing about his
   access changes.
9. "stock for the usual". His two usual products, Kuching first.
10. "I want to talk to a real person". Handover to Aina carrying what they were just
    discussing.

At no step does he get a bare refusal, silence, or an error text.

### B. Staff looking at what the bot knows

Sidebar > User Management > Contacts > Mr Tan > Chatbot card. Under the existing toggles:
"What the bot knows" (each fact with a CRM / Learned / Said / Staff badge, last seen,
expires), "Recent conversations" (one line per episode, opens Chat History), "Open orders"
(live). Staff add a note, correct a learned fact (it becomes Staff), or delete one (a
countdown on the button, no dialog). Two decisions at most: what to change, and Save.

### C. Operator troubleshooting a turn

Chat History > a turn. The Memory panel shows focus, profile and episodes before and after,
the episode written by this turn (if any), and the context report: est. tokens per layer and
what was dropped. The `understood` stage shows prompt and completion tokens.

### D. Owner watching the cost

After S3 ships, the token query (plan 8.4) over the first three weekdays shows p95 prompt
tokens per turn not higher than before, and zero recall re-parses.

## Owner decisions this UAC assumes (the plan's recommendations)

| Q | Recommendation assumed |
|---|---|
| Q1 | Memory ON by default for every contact; the per-contact toggle becomes an opt-out (supersedes D3 "global default off"). |
| Q2 | An episode closes on a topic switch or after a 30-minute gap. |
| Q3 | Episode summaries are deterministic (from the turns' trace), no LLM call, no figures. |
| Q4 | Each parse gets the last 3 episode summaries of the last 30 days and the live episode's last 3 earlier messages. |
| Q5 | The vector recall re-parse is deleted; embeddings keep being written for the n8n search route. |
| Q6 | Facts the dealer states (closed key list) are saved at once as `Said`, hints only, staff can delete. |
| Q7 | Retention: episodes and learned facts 90 days after last seen; stated facts 180 days; staff facts never. |
| Q8 | Token rule: the static prompt may not grow (addendum paid by cuts); user block hard cap 1,800 est. tokens; production p95 not higher than before. |
| Q9 | Out-of-boundary replies: the LLM writes only the acknowledgement; facts and offers come from data. |
| Q10 | Every bot turn not under human takeover sends a visible line. |
| Q11 | Memory card: `memory_default`, `episode_retention_days`, `episode_gap_minutes`; `profile_fields` and `focus_reset_events` removed. |
| Q12 | The staff screen lives inside the existing Chatbot card on the contact page. |
| Q13 | A commercial ask (discount, credit, price exception) is handed to the linked salesperson; everything else to the domain's team. |
| Q14 | "Enterprise Claude Code" (write actions) becomes its own ideation issue; not in this lane. |
