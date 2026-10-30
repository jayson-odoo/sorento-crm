# UAC: Agentic P3 - write actions in the console Agent tab

Plan: `PLAN-agentic-p3-writes-30oct.md`. Card: `CARD-agentic-p2-p3-30oct.md` (owner answers 30 Oct ~11:10).

| AC | Given / When / Then | Evidence |
| --- | --- | --- |
| AC01 | A contact with the Agent switch on and a linked user holding `sales.customer_asks.edit` asks in the Agent tab to mark one of their customer asks done with a note. The agent finds the ask and replies with a proposal listing that change; the ask is unchanged in the CRM. | pytest 2; browser |
| AC02 | The user clicks Confirm. The ask is Done with the note, the reply lists it as done, and the ask's history names the linked user (not the integration). | pytest 5; browser |
| AC03 | The same request from a user without the edit permission: the agent says it cannot make that change; no proposal. | pytest 1 |
| AC04 | An ask of another salesperson's customer (user without view all): no proposal; the agent says it cannot find or change it. | pytest 4 |
| AC05 | The ask is changed on the screen between proposal and Confirm: nothing is written; the reply says what changed. | pytest 6 |
| AC06 | Confirm after 10 minutes, after a newer proposal, after Cancel, or twice: nothing (more) is written; the reply says why. | pytest 8-11 |
| AC07 | The Agent switch is turned off, or the user loses the permission, before Confirm: nothing is written. | pytest 7, 12 |
| AC08 | In chat, "yes go ahead" in the next message confirms; the model cannot confirm in the same turn it proposed. | pytest 13 |
| AC09 | One request covering several asks gives one proposal with one line per ask (at most 20); Confirm applies them in order and reports each; a failure stops the rest and says which were done. | pytest 14, 15 |
| AC10 | "Undo that" after a confirmed change proposes the reverse change, confirmed like any other. | pytest (slice 1 read tool) + browser |
| AC11 | Slice 2: create an opportunity, move its stage, mark it Lost with a reason, all by proposal + confirm; Lost without a reason is refused by the CRM's own rule and the reply says so. | pytest slice 2 |
| AC12 | Nothing outside the registered write tools can be changed by the agent (no delete, no order cancel, no prices, no settings, nothing on the user's own contact). | pytest 1 (registry), review |
| AC13 | Console: the proposal shows each line with Confirm and Cancel; after either, the buttons go and the result shows. Usable at 375 px and 1280 px. | vitest + browser |
