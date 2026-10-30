# PLAN: server enforces required fields on form submit (FORM-REQUIRED-SERVER)

Status: Plan (small fix track candidate, no migration, no RBAC change). Lane FORM-REQUIRED-SERVER.

## Problem

Found by PORTAL-P4-REQUESTS (#1953): for stock_inquiry, complaint, purchase_request and
sponsorship_form the server accepts a submit with required fields missing (200, status
submitted, number assigned). Only SubmissionForm's required flags stop it in the UI.

## Fix (to be filled in after code reading)

On SUBMIT only (not draft save), the server checks the same required fields the UI marks
required, per kind, from one source of truth, and refuses with 422 + the list of missing fields.
