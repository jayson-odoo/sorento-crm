# UAC: OI emails routed by raiser

- R1. The handover and undo triggers offer a condition "Raised by" (user picker; is any of / is none of).
- R2. Two enabled project rows, A = raisedBy not in [Agnes], B = raisedBy in [Agnes]: a confirm of Agnes' project OI sends one email through B only; a confirm of Bob's sends one through A only.
- R3. One confirm covering Agnes' and Bob's project OIs sends exactly two emails: Agnes' lines via B, Bob's via A; no line appears in both, no row fires twice.
- R4. Bob's and Carol's lines that match the same rows stay in one email.
- R5. An undo of Agnes' OI goes through B only.
- R6. "Send to purchasing" on Agnes' OI previews and sends through B only (not the oldest project row A).
- R7. A row with no raiser condition keeps matching every raiser (no change on deploy); existing class routing unchanged.
