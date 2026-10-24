# PLAN: PHOTO-ORDER-SCOUT - a photo sent before a text arrives after it

Status: research (size S scout, no product code); behaviour card pending as one crew `--ask`

## Problem (prod, 25 Oct 2026 02:34 MYT)

Verified by crew from n8n executions 21638407 / 21638413 of producer `sorento-main`
(`NwMOBEQ1NW7LVky5`):

| Message | respond.io timestamp | Webhook received | Lag |
| --- | --- | --- | --- |
| Photo (image) | 02:34:25.8 | 02:34:34.8 | 9.1 s |
| Text "Check stock" | 02:34:28.8 | 02:34:32.4 | 3.6 s |

The text reached the bot 2.4 s before the photo, so the bot answered "Check stock" from a stale
open task, then answered the photo separately. The photo payload had `isPending=false`.

Owner rulings: no blanket hold on texts, no merge window. Photo-first only IF we can know a
photo is coming.

## Research questions

1. respond.io webhook/event model for incoming media: any earlier event or payload field
   (`isPending=true`, a status event) that fires before the media is ready?
2. Does our n8n producer trigger or the CRM webhook filter or ignore `isPending` / other event
   types?
3. respond.io API: can we list a contact's latest messages (endpoint, auth, rate limits, does a
   pending media message appear before its webhook)?
4. Options: A) signal-gated hold, B) no wait, re-answer the text for a late photo; plus the
   turn-age / state rule for a bare "check stock" reusing a stale open task.

## Findings

(in progress)
