# Ideation `ideate` turn - end-to-end SORENTO simulation transcript

Drives `POST /api/v1/external/ideation/turn` via FastAPI TestClient across a multi-turn WhatsApp conversation. The endpoint, request/response schemas, and `handle_turn` session_vars merge logic are REAL; the brain extractor and `create_idea` are stubbed (no live LLM / shared-service).

- create_idea mode: **STUBBED create_idea (D-CONFIRM sequence)**
- Pre-existing CRM key seeded on every contact: `referenced_result_set` = `[{"id": "prev-stock-query", "sku": "ABC-123"}]`

---

## T1 incomplete -> collecting (pointer set)
- Contact: `rio-alice-001`

**USER (WhatsApp):** I've got an idea - the system should remind me before a quotation expires

**Brain extraction {fields, remove, confirm}:** `{"fields": {"what": "remind me before a quotation expires"}, "remove": [], "confirm": false}`

    [PASS] HTTP 200 (got 200)
**Relayed status:** `collecting`
**Relayed reply_text:** Love it. Which module is this about, who benefits, and what's the impact?
**Relayed link:** (none)
**session_vars.ideation:** `{"draft_id": "d-100", "status": "collecting", "missing": ["module", "who", "impact"], "updated_at": "2026-07-19T00:56:59.742960+00:00"}`
**Full session_vars keys:** `["ideation", "referenced_result_set"]`

> First turn: draft_id OMITTED in the create_idea payload; pointer persisted.

    [PASS] status == 'collecting'
    [PASS] no link before complete
    [PASS] session_vars.ideation PRESENT (not cleared)
    [PASS] ideation.status == 'collecting'
    [PASS] ideation.missing == ['module', 'who', 'impact']
    [PASS] ideation carries draft_id
    [PASS] ideation carries updated_at
    [PASS] CRM key `referenced_result_set` intact

---

## T2 partial -> collecting (missing shrinks)
- Contact: `rio-alice-001`

**USER (WhatsApp):** it's mainly for the sales team

**Brain extraction {fields, remove, confirm}:** `{"fields": {"who": "sales team"}, "remove": [], "confirm": false}`

    [PASS] HTTP 200 (got 200)
**Relayed status:** `collecting`
**Relayed reply_text:** Got the sales team. Which module, and what's the impact?
**Relayed link:** (none)
**session_vars.ideation:** `{"draft_id": "d-100", "status": "collecting", "missing": ["module", "impact"], "updated_at": "2026-07-19T00:56:59.745104+00:00"}`
**Full session_vars keys:** `["ideation", "referenced_result_set"]`

> Continuation: draft_id d-100 passed through; missing shrank from 3 -> 2.

    [PASS] status == 'collecting'
    [PASS] no link before complete
    [PASS] session_vars.ideation PRESENT (not cleared)
    [PASS] ideation.status == 'collecting'
    [PASS] ideation.missing == ['module', 'impact']
    [PASS] ideation carries draft_id
    [PASS] ideation carries updated_at
    [PASS] CRM key `referenced_result_set` intact

---

## T3 rest supplied -> REVIEW (echo + confirm ask; NOT cleared)
- Contact: `rio-alice-001`

**USER (WhatsApp):** module is Order Management and it'd save us chasing expired quotes

**Brain extraction {fields, remove, confirm}:** `{"fields": {"module": "Order Management", "impact": "saves chasing expired quotes"}, "remove": [], "confirm": false}`

    [PASS] HTTP 200 (got 200)
**Relayed status:** `review`
**Relayed reply_text:** Here's what I have - What: remind before a quotation expires | Who: sales team | Module: Order Management | Impact: saves chasing expired quotes. Reply 'confirm' to submit, or tell me what to change.
**Relayed link:** (none)
**session_vars.ideation:** `{"draft_id": "d-100", "status": "review", "missing": [], "updated_at": "2026-07-19T00:56:59.746744+00:00"}`
**Full session_vars keys:** `["ideation", "referenced_result_set"]`

> All fields in -> REVIEW gate. Pointer KEPT (never cleared before confirm).

    [PASS] status == 'review'
    [PASS] no link before complete
    [PASS] session_vars.ideation PRESENT (not cleared)
    [PASS] ideation.status == 'review'
    [PASS] ideation.missing == []
    [PASS] ideation carries draft_id
    [PASS] ideation carries updated_at
    [PASS] CRM key `referenced_result_set` intact

---

## T4 'change team to Operations' -> review re-echoed (merged)
- Contact: `rio-alice-001`

**USER (WhatsApp):** actually change the team to Operations

**Brain extraction {fields, remove, confirm}:** `{"fields": {"who": "Operations"}, "remove": [], "confirm": false}`

    [PASS] HTTP 200 (got 200)
**Relayed status:** `review`
**Relayed reply_text:** Updated Who -> Operations. What: remind before a quotation expires | Who: Operations | Module: Order Management | Impact: saves chasing expired quotes. Confirm?
**Relayed link:** (none)
**session_vars.ideation:** `{"draft_id": "d-100", "status": "review", "missing": [], "updated_at": "2026-07-19T00:56:59.748274+00:00"}`
**Full session_vars keys:** `["ideation", "referenced_result_set"]`

> Revise while reviewing: fields merged, still REVIEW, pointer persists.

    [PASS] status == 'review'
    [PASS] no link before complete
    [PASS] session_vars.ideation PRESENT (not cleared)
    [PASS] ideation.status == 'review'
    [PASS] ideation carries draft_id
    [PASS] ideation carries updated_at
    [PASS] CRM key `referenced_result_set` intact

---

## T5 'remove the impact' -> collecting re-opened (per schema)
- Contact: `rio-alice-001`

**USER (WhatsApp):** remove the impact, I'm not sure yet

**Brain extraction {fields, remove, confirm}:** `{"fields": {}, "remove": ["impact"], "confirm": false}`

    [PASS] HTTP 200 (got 200)
**Relayed status:** `collecting`
**Relayed reply_text:** Cleared the impact. What's the impact when you're ready?
**Relayed link:** (none)
**session_vars.ideation:** `{"draft_id": "d-100", "status": "collecting", "missing": ["impact"], "updated_at": "2026-07-19T00:56:59.749848+00:00"}`
**Full session_vars keys:** `["ideation", "referenced_result_set"]`

> Removing a required field re-opens COLLECTING; pointer still not cleared.

    [PASS] status == 'collecting'
    [PASS] no link before complete
    [PASS] session_vars.ideation PRESENT (not cleared)
    [PASS] ideation.status == 'collecting'
    [PASS] ideation.missing == ['impact']
    [PASS] ideation carries draft_id
    [PASS] ideation carries updated_at
    [PASS] CRM key `referenced_result_set` intact

---

## T6 add more info -> REVIEW re-echoed (merged)
- Contact: `rio-alice-001`

**USER (WhatsApp):** the impact is it saves us about 2 hours a week

**Brain extraction {fields, remove, confirm}:** `{"fields": {"impact": "saves about 2 hours a week"}, "remove": [], "confirm": false}`

    [PASS] HTTP 200 (got 200)
**Relayed status:** `review`
**Relayed reply_text:** Great. What: remind before a quotation expires | Who: Operations | Module: Order Management | Impact: saves ~2 hours a week. Confirm?
**Relayed link:** (none)
**session_vars.ideation:** `{"draft_id": "d-100", "status": "review", "missing": [], "updated_at": "2026-07-19T00:56:59.751573+00:00"}`
**Full session_vars keys:** `["ideation", "referenced_result_set"]`

> Re-supplying the field returns to REVIEW; impact merged in.

    [PASS] status == 'review'
    [PASS] no link before complete
    [PASS] session_vars.ideation PRESENT (not cleared)
    [PASS] ideation.status == 'review'
    [PASS] ideation.missing == []
    [PASS] ideation carries draft_id
    [PASS] ideation carries updated_at
    [PASS] CRM key `referenced_result_set` intact

---

## T7 'yes confirm' -> COMPLETE + link; pointer CLEARED
- Contact: `rio-alice-001`

**USER (WhatsApp):** yes, confirm that

**Brain extraction {fields, remove, confirm}:** `{"fields": {}, "remove": [], "confirm": true}`

    [PASS] HTTP 200 (got 200)
**Relayed status:** `complete`
**Relayed reply_text:** Logged! You can track your idea here.
**Relayed link:** https://fe-sorento.foundryx.my/ideas/idea-9001
**session_vars.ideation:** `null`
**Full session_vars keys:** `["referenced_result_set"]`

> Explicit confirm -> COMPLETE + product-domain link; session_vars.ideation CLEARED; CRM key intact.

    [PASS] status == 'complete'
    [PASS] link present on complete
    [PASS] session_vars.ideation CLEARED
    [PASS] CRM key `referenced_result_set` intact

---

## T8 (Bob) one-shot complete FIRST turn -> still REVIEW (not complete)
- Contact: `rio-bob-002`

**USER (WhatsApp):** Idea: in Inventory, warehouse ops should get a low-stock alert - it prevents stockouts.

**Brain extraction {fields, remove, confirm}:** `{"fields": {"what": "low-stock alert", "who": "warehouse ops", "module": "Inventory", "impact": "prevents stockouts"}, "remove": [], "confirm": false}`

    [PASS] HTTP 200 (got 200)
**Relayed status:** `review`
**Relayed reply_text:** Everything's here - What/Who/Module/Impact all set. Reply 'confirm' to submit.
**Relayed link:** (none)
**session_vars.ideation:** `{"draft_id": "d-200", "status": "review", "missing": [], "updated_at": "2026-07-19T00:56:59.754752+00:00"}`
**Full session_vars keys:** `["ideation", "referenced_result_set"]`

> Even a first turn with EVERY field routes through REVIEW; no auto-complete.

    [PASS] status == 'review'
    [PASS] no link before complete
    [PASS] session_vars.ideation PRESENT (not cleared)
    [PASS] ideation.status == 'review'
    [PASS] ideation carries draft_id
    [PASS] ideation carries updated_at
    [PASS] CRM key `referenced_result_set` intact

---

## T9 (Bob) 'confirm' -> COMPLETE + link; pointer CLEARED
- Contact: `rio-bob-002`

**USER (WhatsApp):** confirm

**Brain extraction {fields, remove, confirm}:** `{"fields": {}, "remove": [], "confirm": true}`

    [PASS] HTTP 200 (got 200)
**Relayed status:** `complete`
**Relayed reply_text:** Submitted! Track it here.
**Relayed link:** https://fe-sorento.foundryx.my/ideas/idea-9002
**session_vars.ideation:** `null`
**Full session_vars keys:** `["referenced_result_set"]`

> Confirm closes Bob's draft: COMPLETE + link, pointer cleared.

    [PASS] status == 'complete'
    [PASS] link present on complete
    [PASS] session_vars.ideation CLEARED
    [PASS] CRM key `referenced_result_set` intact

---

## Result
- All status / session_vars / CRM-key assertions PASSED.
