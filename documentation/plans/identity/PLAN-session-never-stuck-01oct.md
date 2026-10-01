# PLAN: session never stuck (SESSION-NEVER-STUCK)

Status: Plan (small fix track, no migration) - investigation in progress

## Journey

Owner, viewing as another user (Kah Xin), opens the packing-list page. The page load spins and tab
clicks highlight but never change the page, until the owner signs out and back in. The server
answered in 0.2 s, so the hang is client side: an expired or invalid session token, or a stale
impersonation, loops instead of ending.

## Rule

A failed session (401 on the staff token) or an invalid view-as target ends in exactly ONE
redirect to sign-in with the return URL, impersonation cleared, no infinite spinner, no request
storm.

## Findings

(filled in as the loop is located, with file:line)
