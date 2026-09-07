"""Shared ingest rules, one function per decision, imported by every channel
that needs it (manual service, xlsx importer, ESB masters/document ingest) so
there is never a second copy to drift. See
documentation/plans/_archive/autocount/PLAN-ingest-parity-standardisation.md section 2.1.
"""
