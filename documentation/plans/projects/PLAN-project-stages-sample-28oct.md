# PLAN: project pipeline stages incl. Sample Submission, via the status graph

Status: Plan - behaviour card being drafted (lane PROJECT-STAGES-SAMPLE, size M). Track TBD after the card.

## Owner ask (28 Oct, verbatim)

"i think need to have 1 state is sample request, maybe can use our status graph right, cause I want to move
progressively to sample request like mentioned in this document"

Document stages ("2. Pipeline Stages (Overview)"): 1 Project Registration, 2 Spec-in / Quotation,
3 Sample Submission, 4 Final Negotiation, 5 Sponsorship, 6 Purchase Order (PO).

## Measured today

Status graph rows, entity `project`, global scope (dev copy `sorento_cagent_stack` and crew dev DB, same rows):

| key | label | sort | flags | win % | stale days |
| --- | --- | --- | --- | --- | --- |
| identified | Identified | 0 | | 10 | 21 |
| registered | Registered | 1 | initial, default | 25 | 30 |
| specified | Spec In | 2 | | 40 | 21 |
| sample_submission | Sample Submission | 4 | | 75 | 7 |
| final_negotiation | Final Negotiation | 5 | (created 15 Oct, no edges) | - | - |
| sponsorship_form | Sponsorship Form | 6 | (created 15 Oct, no edges) | - | - |
| po_received | PO Received | 7 | terminal | 100 | - |
| lost | Lost | 8 | terminal | 0 | - |
| dormant | Dormant | 9 | terminal | 0 | - |

16 edges, all `trigger_mode = manual`. No edge INTO `sample_submission`, `final_negotiation` or
`sponsorship_form`, so a Spec In project can only go to PO received, Back to registered, Mark lost,
Mark dormant: the jump the owner saw on PPF2610003.

Code map: (filled from the explorers' file:line findings)

## Proposal

(behaviour card; build only after crew relays the answers)
