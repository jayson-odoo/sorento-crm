# Kill matrix (TDD evidence, ESCALATION-CONTROL)

Most tests in this lane were written after the code (the feature skill's red-first order was
not followed from the start; see the PR note). To prove each behaviour is guarded anyway,
`killmatrix.py` breaks the implementing line of each behaviour, runs the test that should
guard it, and restores the file. Every row went red. K6 and K8 first stayed green (the
engine guard and the apply wrapper also covered them); direct tests were added and re-run.
New behaviour in the last round (security S1/S2, grill Q4, label) was written red-first:
the tests failed on the previous code before the fix.

| Behaviour | Broken in | Result | Test outcome |
| --- | --- | --- | --- |
| K1 override wins | app/services/escalation_policy.py | RED (guarded) | 1 failed, 13 warnings in 16.24s |
| K2 merge: any type allows | app/services/escalation_policy.py | RED (guarded) | 2 failed, 2 passed, 126 warnings in 40.08s |
| K3 seed: every ...Dealer type | alembic/versions/esc1_0001_escalation_allowed.py | RED (guarded) | 1 failed, 1 passed, 13 warnings in 0.53s |
| K4 profile carries the policy | app/services/chatbot/turn_runtime.py | RED (guarded) | 1 failed, 13 warnings in 12.46s |
| K5 offer gates read offers_escalation | app/services/chatbot/turn/state.py | RED (guarded) | 6 failed, 2 passed, 126 warnings in 37.16s |
| K6 stale offer closed on entry | app/services/chatbot/turn/apply.py | RED (guarded) | 1 failed (test_apply_closes_an_open_escalation_offer_on_entry_for_a_barred_contact) |
| K7 forced ask blocked (engine guard) | app/services/chatbot/engine.py | RED (guarded) | 1 failed, 126 warnings in 34.28s |
| K8 _lane marks the barred lane | app/services/chatbot/turn/apply.py | RED (guarded) | 3 failed (test_lane_blocks_every_forced_door_for_a_barred_contact) |
| K9 fallback team gated | app/services/chatbot/engine.py | RED (guarded) | 1 failed, 14 warnings in 17.99s |
| K10 casual lane strip | app/services/chatbot/engine.py | RED (guarded) | 1 failed, 14 warnings in 17.20s |
| K11 backstop strip | app/services/chatbot/escalation_control.py | RED (guarded) | 3 failed, 1 passed, 13 warnings in 0.79s |
| K12 trace wording | app/services/chatbot/trace.py | RED (guarded) | 1 failed, 13 warnings in 0.65s |
| K13 PUT override (null = inherit) | app/api/v1/user_management/contacts.py | RED (guarded) | 2 failed, 131 warnings in 39.99s |
| K14 contact response fields | app/services/contact_service.py | RED (guarded) | 2 failed, 4 passed, 131 warnings in 35.51s |
| K15 access type update | app/services/contact_access_type_service.py | RED (guarded) | 1 failed, 131 warnings in 43.78s |
| K16 unbarred contacts untouched | app/services/chatbot/turn/state.py | RED (guarded) | 3 failed, 126 warnings in 34.61s |
