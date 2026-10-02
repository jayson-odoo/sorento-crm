# PLAN: SO-number ask answers about that SO only (SO-NUMBER-ASK)

Status: in progress (small fix track: no migration, no auth/RBAC change, diff well under 300 lines)

## Bug

A dealer asks `status of SO422056` in the chatbot. The bot correctly skips the period question, then
sends a 20-row DO dump across all of the dealer's linked customers and closes with
"I could not find SO422056." (tester note on PR #1433, "E3 SO number").

## Goal

- SO exists and is in the contact's scope: show that SO's status (and its DOs when linked).
- SO not found / out of scope: one "I could not find SO..." line, no DO dump, no other customers' data.
- Never dump unrelated DOs.

## Root cause

(filled in once traced, with file:line)

## Tests

Red-first pytest reproducing the dump, then the fix.
