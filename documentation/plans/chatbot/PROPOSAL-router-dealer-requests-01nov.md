# PROPOSAL: router wording for dealer requests (AGENTIC-WA-W2 slice 1)

Status: PROPOSED, not published. Gate run by crew decides (`scripts/gate_router_variant_b.py`). No stored prompt is
changed on any database by this lane. Track: L (part of #2072).

## Why

Slice 1 lets a dealer send a stock inquiry, add or remove a note on their own request, withdraw a fresh inquiry and
list their requests (`PLAN-agentic-wa-w2-01nov.md`). On WhatsApp the router decides per message (cut-off 0.70, owner
ruling), and only the agent can make these requests. Today's published `chatbot_router` v1 (md5 `355002bd`, the text in
`ai_prompt_registry._chatbot_router_fallback`) tells Jev that a named product code with stock / ETA belongs to the bot
and that the agent is `not_for` "a plain stock, ETA, price or file check". Only "any request to change, update, approve
or record something" points a write at the agent.

Measured by crew on the dev copy (PR #2072 comment 6562121453, 21 rows, one Jev call each, jev-1.14.0):

| Text | Dealer asks reaching the agent | Stock-check controls on the bot |
| --- | --- | --- |
| v1 (today) | 8/18 | 3/3 |
| v1 + variant B | 16/18 | 3/3 |

B still misses `si-1` ("can I get 40 pcs SRT5733 by 15 Dec 2026 for project Test Tower?", chat at 0.02) and the
Malay `si-6`. Single runs drift, so B is not proven; earlier router proposals measured worse on the baseline
(`PROPOSAL-router-text-panel-1nov.md`), so the gate decides.

## The change: three sentences appended (semantic, no word list)

- `agent.also` + "Also any request for the team to act for the person: send, raise or file something (a stock or lead
  time inquiry to a team), add a note to one of their own requests, withdraw or undo what they just sent, and a
  question about the requests they sent."
- `agent.not_for` + "(A check of what is in stock is the bot's; asking the team to check or confirm is not.)"
- `chat.not_for` + "A request to send or file something to a team, or to change or undo something already sent."

`instructions` and every other sentence are v1 unchanged.

## The gate (set before the run)

`python -m scripts.gate_router_variant_b --baseline <rows.jsonl> --contact <respond_io_id> --json out.json`:

- crew's router baseline rows (the 50 + 30 AGENTIC-UNIFY used), v1 and B, once each;
- the 21 W2 rows, v1 and B, twice each (reported, not gated).

PASS = on every baseline set B gets no fewer rows right than v1, at the 0.70 floor AND on Jev's own pick. Read only:
no usage row, no turn, no prompt version. About 244 Jev calls for 80 baseline rows.

## The question for the owner (si-1)

When a dealer asks "can I get 40 pcs X by 15 Dec for project Y?", should it reach the team as a stock inquiry (the
agent proposes one and the dealer says yes), or stay a stock check the bot answers? Recommendation: keep it a stock
check on the bot, because most such asks want an answer now and the inquiry is for when the dealer asks the team to
act; the guide and the hand test then use an explicit ask ("please send a stock inquiry ...").

## If the gate passes: publishing (admin, no release)

1. Sidebar: AI Assistant > Prompts, open `chatbot_router`.
2. On the Edit tab, replace all the text with the JSON block below. Commit message, then **Save as new version** (v2).
3. With v2 showing, press **Publish v2** and confirm. The next router call uses it.
4. Undo: Version history, pick v1, **Publish v1**.

Needs `system.ai_assistant_settings.edit`. After publishing, a follow-up PR updates
`_chatbot_router_fallback` to the same text so new copies seed it, and turns the 21 rows into a guard.

```json
{
  "instructions": "A staff member or a dealer sent the latest message to the company's WhatsApp sales-support assistant. Two sides can answer it. Decide which side should answer the latest message, reading the recent exchanges for context.",
  "criteria": {
    "chat": {
      "what": "The quick-lookup bot. One lookup about a named product code (or a list of product codes), where each answer is one simple fact: stock, incoming or ETA, last arrival, a customer's orders or deliveries, outstanding orders, list price or cost, a form, a product file, drawing, certificate or picture, a promotion, a catalogue.",
      "also": "Greetings, thanks, casual talk, a menu answer such as a number or an option name, a short follow-up to the bot's last answer, and anything too unclear to act on.",
      "not_for": "Totals, rankings, comparisons, breakdowns or anything that needs several facts combined. A request to send or file something to a team, or to change or undo something already sent."
    },
    "agent": {
      "what": "The analyst agent with tools. The ask needs several facts combined or calculated: totals or counts over a period, a ranking such as top 10, a comparison, a breakdown per salesperson, customer, supplier or month, a list of which customers, dealers or salespeople match something, a why or an explanation drawn from the records, or a question that names a product category, product type, brand or supplier instead of a product code, so the products must be found first.",
      "also": "A follow-up to the agent's own previous answer, and any request to change, update, approve or record something. Also any request for the team to act for the person: send, raise or file something (a stock or lead time inquiry to a team), add a note to one of their own requests, withdraw or undo what they just sent, and a question about the requests they sent.",
      "not_for": "A plain stock, ETA, price or file check, even for many products at once. (A check of what is in stock is the bot's; asking the team to check or confirm is not.)"
    }
  }
}
```
