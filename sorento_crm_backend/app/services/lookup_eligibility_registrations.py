"""Eligibility is now schema-driven (see ``app.services.lookup_eligibility``).

This module is kept as a no-op import target for backwards compatibility with
``app.main`` and any external consumers. Add a ``register_lookup_eligible``
call here only if you need to override the metadata-derived label for a
specific (table, column) pair.
"""
