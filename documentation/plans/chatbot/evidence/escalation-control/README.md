# ESCALATION-CONTROL browser evidence (PR #1406, 30 Sep 2026)

agent-browser 0.27.0, headless Chromium (`/opt/pw-browsers/chromium-1194`, via
`AGENT_BROWSER_EXECUTABLE_PATH`), session `esc`, in the lane's cloud sandbox. Stack: backend on
:8000 against a private database `sorento_browse` (built by `scripts.bootstrap_env`, stamped at
`esc1_0001_escalation_allowed`), frontend `npm run dev` on :3000. The `full_suite` module bundle
was installed so every sidebar group renders.

Seed (direct SQL, no business data): superadmin `esc.admin@sorentocrm.dev`; access types
Sorento Office (allows), Sorento Dealer (blocks), Mocha Dealer (blocks), Mocha Office, Cabana
Office, Cabana Dealer (blocks), End User X, NL Dealer (blocks); contacts "ZZT Mr Loo" (the
owner's hand-test shape: Sorento/Mocha/Cabana Office + Dealer + End User) and "ZZT Mocha Dealer
Only" (Mocha Dealer + Cabana Dealer).

Every screen was reached by sidebar clicks from `/`: Users & Access > Access > Contact Access
Types, and Users & Access > People > Internal Users > contact > Chatbot tab (then the record's
Next contact button). `get url` was read after each navigation.

| Shot | Width | What it shows |
| --- | --- | --- |
| 01 | 1280 | Contact Access Types list |
| 02 | 1280 | Edit Mocha Dealer: "Can escalate to a person" unticked |
| 03 | 1280 | Add type, name "Kedah Dealer": the box starts unticked (grill Q4); renaming it "Kedah Office" ticks it (read off the snapshot) |
| 04 | 1280 | ZZT Mr Loo, Chatbot tab: "(inherit: allowed via Sorento Office)", "Inherited: allowed via Sorento Office" |
| 05 | 1280 | Mr Loo set to Blocked: "Own setting · inherited: allowed via Sorento Office"; the API then read `escalation_allowed: false`; cleared back to inherit (API: null) |
| 06 | 1280 | ZZT Mocha Dealer Only: "Inherited: blocked via Mocha Dealer" |
| 07 | 375 | The same Chatbot tab at 375: nothing clipped, page scrollWidth 360 (only the facts grid scrolls in its own box) |
| 08 | 375 | Contact Access Types list at 375, page scrollWidth 360 |
| 09 | 375 | Edit Mocha Dealer at 375, page scrollWidth 375 |

Saves through the UI: ticking the box on Mocha Dealer and pressing Update at 1280 sent
`PUT /api/v1/user-management/contact-access-types/mocha_dealer` (200) and the API read `true`;
unticking it at 375 and Update read `false` again (restored).

Not covered here: the Chatbot Console. It needs a live parser model key, and this sandbox has
none (UNVERIFIED in the browser). The chatbot behaviour is covered by the engine tests in
`sorento_crm_backend/tests/chatbot/test_escalation_control.py` (real `engine.run_turn`, parser
stubbed) and by the owner's hand test on the crew copy.
