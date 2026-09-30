import subprocess, sys, pathlib
B = pathlib.Path("/home/user/sorento-crm/sorento_crm_backend")
T = "tests/chatbot/test_escalation_control.py"
A = "tests/chatbot/test_escalation_control_api.py"
M = "tests/test_migration_esc1_0001_escalation_allowed.py"
KILLS = [
 ("K1 override wins", "app/services/escalation_policy.py", "    if override is not None:\n", "    if False:\n", T+"::TestResolution::test_the_contact_override_wins_both_ways"),
 ("K2 merge: any type allows", "app/services/escalation_policy.py", "allowed=bool(allowing)", "allowed=len(allowing) == len(ordered)", T+"::TestMergeAcrossAccessTypes"),
 ("K3 seed: every ...Dealer type", "alembic/versions/esc1_0001_escalation_allowed.py", "DEALER_NAME_SQL = \"name ~* '(^|\\\\s)dealer\\\\s*$'\"", "DEALER_NAME_SQL = \"lower(name) = 'sorento dealer'\"", M),
 ("K4 profile carries the policy", "app/services/chatbot/turn_runtime.py", '    return {"escalation_allowed": policy.allowed}', "    return {}", T+"::TestResolution::test_the_profile_carries_it"),
 ("K5 offer gates read offers_escalation", "app/services/chatbot/turn/state.py", "    return not is_staff_profile(profile) and not escalation_barred(profile)", "    return not is_staff_profile(profile)", T+"::test_every_offer_builder_is_silent_for_a_barred_dealer"),
 ("K6 stale offer closed on entry", "app/services/chatbot/turn/apply.py", "    open_question, _dropped = without_escalation(state.pending)", "    open_question, _dropped = state.pending, None", T+"::test_apply_closes_an_open_escalation_offer_on_entry_for_a_barred_contact"),
 ("K7 forced ask blocked (engine guard)", "app/services/chatbot/engine.py", '        and turn_state.escalation_barred(getattr(state_out, "profile", None))\n    ):', '        and False\n    ):', T+"::TestDealerIsNeverOfferedAndCannotForce::test_asking_for_a_person_gets_the_salesman_line_and_no_hand_off"),
 ("K8 _lane marks the barred lane", "app/services/chatbot/turn/apply.py", '    if barred and lane == "escalation":\n        return "escalation_barred"', '    if False:\n        return "escalation_barred"', T+"::test_lane_blocks_every_forced_door_for_a_barred_contact"),
 ("K9 fallback team gated", "app/services/chatbot/engine.py", "        if turn_state.escalation_barred(profile)\n        else", "        if False\n        else", T+"::TestFallbackLane::test_a_barred_contact_is_offered_no_team"),
 ("K10 casual lane strip", "app/services/chatbot/engine.py", "        stripped, _question, offered = escalation_control.strip_text(text, None, state.profile)\n        if offered:", "        stripped, _question, offered = escalation_control.strip_text(text, None, state.profile)\n        if False:", T+"::TestFallbackLane::test_a_clarifier_that_writes_an_escalate_sentence_is_stripped_before_sending"),
 ("K11 backstop strip", "app/services/chatbot/escalation_control.py", "    if not offered:\n        return text, question, False", "    return text, question, False", T+"::TestStripOffers"),
 ("K12 trace wording", "app/services/chatbot/trace.py", '    if branch_kind == "out_of_scope" and lane == "escalation_barred":', '    if False:', T+"::TestNamedTeamAndTrace::test_the_trace_says_the_escalation_was_withheld"),
 ("K13 PUT override (null = inherit)", "app/api/v1/user_management/contacts.py", '        if "escalation_allowed" in body.model_fields_set:', "        if body.escalation_allowed is not None:", A+"::test_put_sets_the_override_and_null_clears_it"),
 ("K14 contact response fields", "app/services/contact_service.py", '            "escalation_allowed_inherited_from": inherited_escalation.source_label,', "", A),
 ("K15 access type update", "app/services/contact_access_type_service.py", "            row.escalation_allowed = bool(data[\"escalation_allowed\"])", "            pass", A+"::test_the_access_type_attribute_round_trips"),
 ("K16 unbarred contacts untouched", "app/services/chatbot/turn/state.py", '    return getattr(profile, "escalation_allowed", True) is False', "    return True", T+"::TestUnbarredContactsAreUnchanged"),
]
only = sys.argv[1:]
for name, f, a, b, test in KILLS:
    if only and name.split()[0] not in only: continue
    p = B / f; orig = p.read_text()
    assert orig.count(a) == 1, (name, orig.count(a))
    p.write_text(orig.replace(a, b))
    try:
        r = subprocess.run(f"SORENTO_ENV_FILE=.env.ci-tests timeout 900 venv/bin/pytest -q -p no:cacheprovider '{test}' 2>&1 | tail -1", shell=True, cwd=B, capture_output=True, text=True)
        line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "?"
        verdict = "RED (guarded)" if ("failed" in line or "error" in line) else "GREEN (NOT guarded)"
        print(f"{name} | {f} | {verdict} | {line}", flush=True)
    finally:
        p.write_text(orig)
