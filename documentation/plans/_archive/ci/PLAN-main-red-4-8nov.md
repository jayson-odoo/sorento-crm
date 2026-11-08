# PLAN: main red after the agent-wave merges (MAIN-RED-4, 8 Nov 2026)

Status: done. Small fix track (tests only expected, no migration, no RBAC change).

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

- 3 agent tests: #2244 renamed `batch.schema_for` to `batch_tool_schema`
  (`app/services/chatbot/agent/batch.py:53`, retired-name guard
  `tests/chatbot/test_rearch_s0_parser_schema.py:19`). #2247, #2252 and #2253 branched before it and
  still called `schema_for`, so they raised AttributeError. The description was never the problem: it
  already asks for every row of the current request (`batch.py:85-86`). The fast PR gate only collects tests,
  so nothing caught it.
- attachment test: #2158 added `has_line_items` / `pasted_text` kwargs to `_build_messages`
  (`app/services/ai_extract/extract_service.py:537-547`), but the test's fake did not accept them. The file is
  listed in `tests/ci_excluded.txt:52`.
- Fix (tests only): call `batch_tool_schema`; w2 test_01 checks enum membership instead of the exact set;
  the fake takes `**_kwargs`. No code change, no migration.
