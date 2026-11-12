# PLAN: Spare-part order request (stock replenishment, no SO)

Status: Plan (discovery in progress; behaviour card goes to crew-ask before any code). Track: L (migration, new flow, approval permissions).

Lane: SPARE-PART-ORDER-REQUEST.

## Goal

A stock-replenishment order request (first use: spare parts) raised without a sales order,
approved through a configurable chain (requester -> approver -> purchasing; the approver may set
or change quantities), then delivered to purchasing as an Order Inquiry with its own type so
purchasing works it in the same place as SO-driven inquiries.

Discovery and the behaviour card follow in the next commit.
