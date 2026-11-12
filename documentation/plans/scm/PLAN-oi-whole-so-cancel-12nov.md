# PLAN: OI-WHOLE-SO-CANCEL - whole-SO cancel and SO delete from AutoCount raise a board item

Status: Plan (behaviour card pending owner answers). Track: M (LEAD pattern).

## Problem

A whole-header cancel on an AutoCount SO (no Cancel SO document) and an AutoCount SO delete
close every live Order Inquiry row on that SO at sync time without any Fulfilment Planning
board item, so CS never confirms and purchasing never hears. Every other cancel path (Cancel
SO document, one line removed) waits on the board and CS Confirm sends CANCEL.

## Goal

Both events raise a board item for CS, like the other cancel paths. Details follow the
behaviour card answers.
