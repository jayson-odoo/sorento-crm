"""Reusable condition-tree rule engine (ported from foundryx-shared-service).

A rule is a nested AND/OR condition tree evaluated against a flat fact dict.
Pure evaluator (no I/O) + a fact registry (whitelisted, ORM-backed resolvers) +
save-time validation + human-readable prose. v1 exposes a single ``promotion``
fact source, consumed by the ``days_before_promotion_end`` automation trigger.
"""
