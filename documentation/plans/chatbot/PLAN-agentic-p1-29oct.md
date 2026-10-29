# PLAN: Agentic phase 1 - read-only agent branch for complex staff turns

Status: Plan (behaviour card being drafted; build waits on owner answers). Lane AGENTIC-P1, branch `claude/agentic-crm-chatbot-p1-fhvvb0`, base origin/main ec29a81c.

Parent: `PLAN-agentic-crm-29oct.md`. P0 (#1979, c9ff4958c9) is on main.

Owner rulings (29 Oct ~22:45): today's parser -> lane path stays the default and unchanged; the agent is a separate
branch that steps in only for complex turns; Claude-Code-style tool loop over typed read tools (no model-written SQL);
reads limited by both user permissions and the contact's chatbot scope; Gemini Flash; P1 read-only.

Behaviour card: to follow in this file.
