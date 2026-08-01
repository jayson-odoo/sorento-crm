"""Form document engine (ported from foundryx-shared-service, plan forms-platform F0).

A form definition is a block document (Page to Section to Field) stored verbatim
as camelCase JSON on ``workflow_form_versions.schema``. Three modules:

- ``schemas``: the document model plus ``validate_form_doc``, the publish gate.
- ``validation``: ``validate_submission``, the server boundary for a submitted
  answer map, plus ``is_visible`` for condition-driven visibility.
- ``computed``: the tokeniser/parser/AST for computed expressions. Tenant-authored
  arithmetic never reaches ``eval``.

Conditions are evaluated by the shared ``app.rule_engine``; visibility always
goes through ``validation.is_visible``, never the bare evaluator, because an
empty ``rules[]`` matches everything there.
"""
