"""SCM reorder-engine simulation harness.

See ``scripts/scm_sim/README.md`` for how to run it. This package is deliberately
import-light at the top level: ``__main__.py`` sets ``DATABASE_URL`` to the sim
database BEFORE importing anything under ``app.*``, so nothing here may import an
``app`` module at module scope of this file.
"""
