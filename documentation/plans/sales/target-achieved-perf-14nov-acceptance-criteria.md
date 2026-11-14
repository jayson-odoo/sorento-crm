# UAC: Invoiced target achievement speed (lane TARGET-ACHIEVED-PERF)

Plan: `PLAN-target-achieved-perf-14nov.md`.

1. Every Invoiced target's Achieved figure (per period, per account) is identical before and
   after the change: 2026 totals per dealer target and account on sorento_prod_1112 compared
   row for row.
2. The Invoiced achievement statement never compares each credited document with every period:
   rows removed by its join filters stay within (credited documents x periods of one target).
3. On sorento_prod_1112: agent_target_summary this_year, target_list this_year and the Targets
   screen dealer tab each finish well under 5 s, warm and cold.
4. When a computed assistant entity (targets, commission) times out, the message no longer tells
   the model to narrow the question with a filter.

## Part 2 (#2419 slice 1; crew answers 14 Nov, from owner rulings)

5. A target question naming an agent (or asked as "my dealers" by an own-only user) computes only
   the targets that agent can be credited on: their agent targets, their teams' targets, and every
   dealer target with ANY counted account of theirs. The rows returned are identical to computing
   everything and filtering after; the achievement statement receives no other target's periods.
   `owner_kind` narrows the same way (not when an agent filter is also named). Status / reached /
   pct filters stay in Python (Q5). Two deliberate exceptions: (a) when the narrowed set is empty,
   everything is computed once so the "Nothing matched" note keeps listing the values that exist
   (if that is refused for the window cap, the note still says nothing matched); (b) the period cap
   counts the narrowed set, so a named-agent question over a wide window answers that window where
   computing everything would have fallen back to the periods containing today.
6. `agent_target_summary` and `target_list` rows carry `remaining_value` = target - achieved,
   floored at 0 (0 once reached; `achieved_pct` shows any over-achievement), computed by the
   server and listed by crm_describe (Q1).
7. The per-question cap counts only crm_query calls that ran (ok, empty or timed out); crm_describe
   and refused calls are free. The cap is 6, a runaway stop only; a refused call is a tool reply,
   the answer still gives its best full result, and the user never sees a "limit" message (Q3, owner
   D4 19:27: "I would rather wait if it is within reason than you say hit limit").
8. The `chatbot_agent` prompt no longer conflicts with the tools: an agent filter on crm_query needs
   no crm_resolve first, and a target question gets the target's own basis only (no "show invoiced,
   delivered and ordered" that the loop refuses). Shipped as an unlabelled candidate version (md5 +
   publish SQL as a crew ask); prod labelling only with the release (Q2).
9. Panel, on a copy of prod data: "how are my dealers' sales this year against their targets?",
   then "and last year?", then a typo version: each answered in 2 model calls, under 35,000 input
   tokens, under 15 s, no timeout, figures equal to the Targets screen. One live x1 run (frozen set
   dev part + these 3 phrasings), cap US$0.50, logged on the crew ledger (Q4).

## Live-run round (crew decision (a), 14 Nov)

10. A target's achieved on `agent_target_summary` counts every period of the target in the window,
    including periods whose target is 0 (they add 0 to the target and nothing to the payout), so
    each row equals the Targets tab for the same periods when the window covers the whole target
    (owner rule: same total everywhere). The note never says the sales of a period of 0 inside a
    target above 0 are left out; a target that is 0 over the whole window keeps the owner's 8 Nov
    rule (no target or achieved shown, named in the note).
11. The crm_query result totals for `agent_target_summary` carry target, achieved and remaining
    sums over all matching rows next to the payout (never summed across amount and quantity), so
    one query answers "sales vs target" (live diagnostic: with payout-only totals the model ran
    crm_query 5 times in one turn).

## Fix round (crew-pass on cca604f9 NOT READY, 14 Nov; owner D4: no answer ends in a timeout or "limit" message)

12. Crew pass, typo question: 6 rounds, 8 tool calls all ok, then the next round's model call started with
    almost no turn time left (`chatbot_agent_max_seconds` 45; a round gets min(60 s, time left), loop.py
    ~1958) and timed out; the turn ended `limited` / `error` with "Stopped: an error" after 55 s.
    (a) A tool round is not started when the turn has less time left than a round needs; with tool results
        in hand the turn goes straight to its final answer from those results: status answered, no
        limit_hit, no "stopped because of an error" sentence, no footer.
    (b) If a round's model call times out anyway while tool results are in hand, the turn still answers
        from those results the same way (no error footer or sentence). With NO tool result yet, today's
        behaviour stays (nothing to answer from).
    (c) Only when the final answer itself fails does the turn end in an error.
