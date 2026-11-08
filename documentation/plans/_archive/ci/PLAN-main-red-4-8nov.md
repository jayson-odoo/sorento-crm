# PLAN: main red after the agent-wave merges (MAIN-RED-4, 8 Nov 2026)

Status: in progress. Small fix track (tests only expected, no migration, no RBAC change).

## Failing on origin/main 02db12fd

- tests/chatbot/agent/test_agent_batch_notchanged.py::test_the_tool_asks_for_every_row_of_the_current_request (#2252)
- tests/chatbot/agent/test_agent_bulk_w2_tags.py::test_01_the_batch_tool_offers_both_writes_with_the_slug_and_neither_without (#2247)
- tests/chatbot/agent/test_agent_bulk_w3_agents.py::test_01_the_batch_tool_offers_the_write_only_with_the_slug (#2253)
- tests/test_attachment_field_links.py::test_run_extract_narrows_schema_by_field_subset

## Approach

Reproduce, name the merge that broke each pin, then make each test assert the merged intent
(each write offered only with its slug; the tool asks for every row of the current request)
without pinning the full description text. Code changes only if merged behaviour is wrong.

## Findings

(filled in as the lane runs)
