# PLAN: Sample request two-stage tracking (PS-SAMPLE-TRACKING)

Status: Plan (behaviour card in progress). Track: M lane, cloud.

Scope (owner rulings 2 Nov 2026):

- Stage 1 (Processing): when the sample team receives a request it starts processing and must
  answer whether the requested delivery date can be met, else propose a new date. The salesperson
  sees the answer.
- Stage 2 (Delivery): delivery is the AutoCount DO. If a DO links to a consignment that links to the
  sample request, the request shows Delivered from that link; no manual Delivered when a DO exists.
- Map today's statuses (sample_request.py, board_mounting) onto the two stages.
- Out of scope: 3-month return + auto invoice.

Behaviour card, UAC and slices follow in this file once the card is answered.
