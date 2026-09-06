# Chatbot verification (the console check)

The chatbot has no screen to click, so browser verification cannot cover it. Its equivalent is
`sorento_crm_backend/scripts/chatbot_console_check.py`: a YAML file of real turns, run against a
real backend, graded line by line. Every chatbot PR runs the case file against a LANE backend
before the PR is opened, and once against PRODUCTION after the deploy; the output of both goes in
the PR (or the deploy note). A case that fails is a finding to fix or to explain - never one to
soften.

```bash
cd sorento_crm_backend
venv/bin/python scripts/chatbot_console_check.py \
    tests/chatbot/console_cases/2026-09-06.yaml --base-url http://127.0.0.1:8004
```

Every turn is a dry run (`is_test`, `test_run_id`), so nothing outside `chatbot.turns` is written
and no WhatsApp message can leave. The envelope is borrowed from that contact's most recent
`chatbot.turns` row, which is why the script refuses a non-local `--base-url` without `--i-know`:
it reads THIS checkout's database and posts to whatever backend you name, and nothing can check
the two agree. The lane switches (`system_settings.chatbot_business_lane_enabled`,
`chatbot_completed_lanes`) have to be on for the run and restored afterwards - the runner does
that around the run, in a `finally`.

**The case file grows from the n8n side.** Cases come from what the owner actually sent and what
came back: the report from the n8n run is the source, one case per defect, with the expectation
taken from that defect's own red test so the file and the suite say the same thing. A multi-turn
case is a `turns:` list - each reply's session variables feed the next turn as
`previous_conversation_state`, which is how a picker or did-you-mean sequence is checked without
writing session state.

Two limits worth knowing before reading a red line as a defect:

- **The MCP tool search needs `OPENAI_API_KEY`**, which is empty in every local `.env`. Without it
  any turn that has to pick a tool fails with "no embedding provider is configured" and the case
  cannot be graded locally. Those cases are graded on the production run.
- **Access is decided before routing.** A turn whose agent the contact has no grant for (or whose
  `access_agents` row does not exist at all) comes back `access_denied` whatever the lane does.
  That is a data prerequisite, and the check naming it is the check working.
