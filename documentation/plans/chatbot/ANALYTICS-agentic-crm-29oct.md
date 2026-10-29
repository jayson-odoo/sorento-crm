# General analytical capability for Sorento agent

Owner requirement: provide a Claude Code-like analytical experience inside Sorento. Users can ask novel questions; the agent discovers relevant data, queries, computes, checks and explains without a prebuilt report for each question. This is a core capability alongside operational actions, not a replacement for them.

## Existing foundations inspected

Current origin/main services/analytics_connector/datasets.py implements dataset discovery/descriptions and a typed query builder (columns, filters, grouping, measures) over a limited catalog, primarily chat/AI data. It binds values, caps rows/output and applies statement timeouts. views.py provides selected read views and a read-only role. access.py implements short-lived signed, request-bound connector calls resolving an active User, route/tool allowlists, consent checks and audit. These are reuse candidates, not proof of generic per-user row/column enforcement over all CRM tables. The list-query registry likewise covers selected resources. The report engine remains authoritative for established metrics.

## Proposed analytical loop

Understand question -> discover authorized schema and metric definitions -> inspect representative scoped data -> construct query -> validate and execute -> inspect result -> follow-up query or computation -> verify -> explain with evidence. This is dynamic analysis, not a new intent handler for every report.

Proposed capabilities: discover_data, describe_data, run_read_query, inspect_result, analyze_result, create_analysis_artifact. Names are illustrative. Discovery includes types, grain, keys, join cardinality, units, business definitions, freshness and applicable scope. The agent can compose joins, aggregations, window functions and derived calculations across admitted datasets rather than being limited to canned output shapes. There is no promise that every raw table is immediately eligible.

## Query execution boundary

Model-authored read SQL is a proposed implementation option over secured analytical relations, not arbitrary production credentials. Server binds linked-user authority and data scope. Use a constrained DB principal and audited scoped relations/RLS or an equivalently proven mechanism; a model-supplied WHERE company_id is not enforcement. Validate SQL syntax tree, relation/function access, statement count and cost constraints. Read-only transactions alone do not prevent all unsafe function calls or unauthorized reads. Block DDL/DML, external access, unapproved functions and cross-schema/system access. Bound runtime, rows, result bytes, concurrency and cancellation. Database isolation and scoped relations remain authoritative even if SQL validation has a defect. Fail closed where scope parity is unproven.

Treat visible schema names, samples, aggregates, cached results and exports as permission-controlled data. Recheck authority on reuse/download; isolate results by task/user/company. A replica/warehouse may help workload isolation later; freshness must be explicit. Do not mandate an infrastructure migration before measuring needs.

## Meaning and correctness

Keep official metric definitions (for example invoiced net sales, cancellations, credits, currency and document dates) accessible as reusable data definitions/services. Let users ask novel combinations without having the model invent those meanings. Document grain and join cardinality to avoid counting invoice totals once per line. Check row counts, uniqueness, nulls, date boundaries, reconciliation totals, currency/unit consistency and pagination/completeness. Record query, parameters, dataset/definition versions, observation time and result references. Explain measured associations separately from causal hypotheses. Unknown or unavailable evidence is reported, not fabricated. No zero-hallucination guarantee.

## Computation workspace

For analysis beyond SQL, propose an isolated Python process/container operating only on authorized result artifacts. No production database credentials, host filesystem, shell escape, network or package installation. Enforce CPU/memory/time/output limits and task-scoped files; container/process controls, not a Python import blacklist, are the security boundary. Use approved libraries for statistics/charts. Return tables/charts/downloads with scoped access and provenance. This can follow the SQL slice; initial analysis must not depend on unrestricted code execution.

## Context and results

Send schema snippets, metric meanings, bounded summaries and tool feedback to the model. Keep large tables as scoped result artifacts and perform arithmetic in SQL/Python. Expose truncation, sample versus full population and freshness. Follow-up questions reuse query/result references but refresh data when needed. Natural-language summaries cite supporting result sections and offer method details without requiring users to read SQL.

## Delivery and acceptance additions

Frontend mock first: an ordinary analytical question, visible progress, clarifying a real metric ambiguity, table/chart, evidence/method details, follow-up and unavailable-data state. Then tester-first backend slices: (1) authorized discovery plus query execution, (2) iterative analysis and result verification, (3) isolated computation and artifacts. Preserve the repo pipeline and same task identity/runtime.

Required cases: a question absent from existing report routes succeeds over admitted data; cross-domain join with correct grain; multi-turn changed date/metric; unauthorized company/column/schema/aggregate denied; malicious SQL/function/CTE rejected; budget cancellation; no secret access from Python; stale cached results after revocation denied; partial results never summarized as complete; correct totals reconciled to existing report where definitions match; causal uncertainty stated. Held-out tasks need independently computed expected results. Measure numerical accuracy and permission correctness separately from fluency.

Existing domain write tools remain the only path to business mutations. An analysis may inform a requested follow-up action, but SQL/Python analytical tools cannot mutate CRM. No model, data warehouse or sandbox technology is selected yet.
