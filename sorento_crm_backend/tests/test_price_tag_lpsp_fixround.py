"""PRICETAG-LPSP fix round 1: revise keeps the line type, the prompt publish of ptag_0014,
the new slot bindings and the one-query combo match.

Reuses the revise harness of `test_portal_price_tag_revise.py` and the migration loader of
`test_migration_ptag_0014_lpsp.py`.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.portal_revision_service import PortalRevisionService
from app.services.price_tag_request_service import PriceTagRequestService
from tests._pg_fixture import blank_session
from tests.test_migration_ptag_0014_lpsp import _PRE_LPSP_TEXT_FOR_TESTS  # noqa: F401  (see below)
