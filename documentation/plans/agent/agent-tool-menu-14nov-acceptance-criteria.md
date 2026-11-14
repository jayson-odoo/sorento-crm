# UAC: Agent short tool menu + "find more tools" (AGENT-CONTEXT-BUDGET slice 2)

Plan: `PLAN-agent-tool-menu-14nov.md`. Owner decision D1 = (c), 14/11/2026 19:27.
"Staff turn" = a turn whose principal is a user (CRM AI panel, console linked user, WhatsApp linked user).

## Behaviour

- **U1** On a staff turn, step 1 offers only the core set the user may use: plan, answer, crm_tools_load,
  crm_query, crm_describe, crm_resolve, crm_knowledge_search, user_guides_read; plus confirm / cancel when
  a change is waiting; plus (Q1) the tools the previous agent turn of this conversation called.
- **U2** crm_tools_load's description lists every other tool the user may use, one line each
  (`name: plain line`, at most 100 chars), and no tool the user may not use.
- **U3** Calling crm_tools_load with names the user may use makes those tools available from the next
  step for the rest of the turn; a name that is not one of the user's tools is answered "not available"
  and nothing is added.
- **U4** A call to one of the user's tools that was not loaded runs as it does today and adds the tool.
  A call to a tool the user may not use is refused exactly as today.
- **U5** Within a turn the offered list only grows; loaded tools sit after the core set. The confirm tool
  still drops from step 2 on.
- **U6** Contact principal turns and the dealer flow offer exactly today's list.
- **U7** Answers are the same as today for the same question: same figures, same cards, same proposals,
  same refusals. Nothing new appears on any screen.
- **U8** The trace records, per step, the offered tool names count, schema chars (as today) and the names
  loaded so far; agent_context records the core and directory sizes.

## Targets

- **K1** Step 1 schema chars for an all-permissions staff panel turn under 20,000 (today 99,300).
- **K2** Step 1 input under 10,000 tokens on crew's run; p90 per question under 45,000 on the frozen set.
- **K3** Frozen owner-FAIL agent set: no baseline pass now fails (live x1 capped US$0.50, then x3).
- **K4** Median seconds per question not higher than the baseline run.

## Tests (pytest, fake provider, US$0)

- T1 all-permissions staff turn: step-1 tool names == core set (U1).
- T2 directory lists exactly the permitted non-core tools; a low-permission user's directory has no
  complaints / stock / cost tool it lacks (U2).
- T3 load of two permitted names: both schemas present in step 2, after the core set (U3, U5).
- T4 load of a forbidden or unknown name: "not available", schema absent (U3).
- T5 direct call to a permitted, unloaded tool: dispatched once, result returned, tool in step 2 (U4).
- T6 direct call to a forbidden tool: refused as today (U4).
- T7 contact principal turn: step-1 list equal to today's assembly (U6).
- T8 dealer flow: equal to today's dealer list (U6).
- T9 previous-turn tools preloaded on a follow-up (Q1), absent on a new conversation.
- T10 list never shrinks across steps except confirm (U5); confirm still absent from step 2.
- T11 step-1 schema chars under 20,000 for all permissions (K1); trace carries loaded names (U8).

## Hand test (panel, crew test copy)

1. Ask "how many open complaints do I have?": same count as the complaints list filtered to the user.
2. Ask "stock of <a product code>": same figure as the stock screen.
3. Ask to give a contact access to something: the same confirm card as today.
4. On a project page: "compare the quotations", then "which one is cheaper?": same comparison as today.
5. Follow-up "and last month?" after step 1's question: answers without asking again.
6. Trace drawer of each: first step under 10,000 input tokens.

## Questions for crew (at most 5)

- **Q1** Preload the tools the previous agent turn of the conversation called? (a) yes, (b) no.
  Recommendation: (a), because follow-ups ("and last month?") then need no load step; it adds a few tools only.
- **Q2** Core set as in U1? (a) as listed, (b) also crm_report_ask. Recommendation: (a), because
  crm_report_ask is the biggest tool (9,700 chars) and slice 1 moves sales-vs-target to crm_query.
- **Q3** Retire the narrowing (`narrow_after_query`)? (a) retire, (b) keep. Recommendation: (a), because
  with a short core set it saves almost nothing and a list that only grows keeps the cache prefix stable.
- **Q4** Contact principal and the old AI assistant stay out of scope? (a) yes, (b) no. Recommendation: (a),
  because the customer list is already small (9 tools) and the old assistant uses another code path.
- **Q5** Live check: crew runs the frozen agent set locally, x1 capped US$0.50 then x3 before merge?
  (a) yes, (b) other. Recommendation: (a), as briefed.
