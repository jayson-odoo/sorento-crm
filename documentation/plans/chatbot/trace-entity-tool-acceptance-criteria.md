# UAC: TRACE-ENTITY-TOOL

- AC-1: A business-lane stock-check turn's trace drawer shows "Tool" with the tool's name and its ms,
  even though the fetch step wrote a later domain-only tool event.
- AC-2: The drawer shows an "Entity match" section: each typed word, the codes it matched (at most
  10, then "+N more"), the match tier, and the words nothing matched.
- AC-3: The span pass lists a code span as "sent to the code lookup", never "skipped".
- AC-4: A turn with no earlier turn reads "First message in this conversation"; with no later
  turn, "No later message yet". "Not recorded" stays only for a real gap.
