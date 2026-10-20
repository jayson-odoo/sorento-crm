# CARD: CHAT-LATENCY-SCOUT, where slow check_stock turns spend ~9s outside the LLM (20 Oct)

Status: scouting (small fix track, no behaviour change). Report first, build only on crew's go.

## Question

Prod 14-20 Oct: 344 turns over 10 s averaged 12.7 s, parser LLM only 3.4 s of it. 234 of the
344 are inventory `check_stock`. Where does the remaining ~9 s go?

## Method

Read the turn pipeline (engine, turn runtime, lanes business fetch, stock tool, stock
visibility policy, MCP calls), then time each stage in a sandbox run against seeded stock data
at realistic volume. Findings, stage table and fixes land below.
