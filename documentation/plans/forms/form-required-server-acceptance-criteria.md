# UAC: server enforces required fields on form submit (FORM-REQUIRED-SERVER)

Plan: `PLAN-form-required-server-30oct.md`. Kinds: stock_inquiry, complaint, purchase_request,
sponsorship_form.

- R1. Submitting a blank draft of any of the 4 kinds is refused with 422, message "Fill in the
  required fields before submitting.", `detail` listing every required field. The row stays a
  draft with no document number.
- R2. With one required field empty (or whitespace only), the 422 names that field alone.
- R3. A complaint without at least one product line is refused, naming `product_lines`.
- R4. A complete draft submits as before (status, number, SLA, notifications unchanged).
- R5. A submit whose body fills the missing fields goes through (the check reads the row after
  the body is applied).
- R6. Saving a draft never checks required fields.
- R7. A portal revise refuses an empty required field the contact can edit; fields frozen on
  revise (the requestor) are exempt, since the contact cannot fill them there. On main the
  revisable kinds' only required field is frozen, so this bites once #1953 adds the complaint
  revise.
- R8. A row that cannot be submitted for its status keeps its own refusal ("Cannot submit ...").
- R9. The server list equals SubmissionForm's `required: true` flags per kind; a drift fails CI.
- R10. External / chatbot / MCP create paths are unchanged.
