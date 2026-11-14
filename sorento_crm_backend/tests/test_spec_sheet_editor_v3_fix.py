"""SPEC-SHEET-PARITY-B2 v3 fix round (review S3, N2). Written test-FIRST.

- S3: "Apply to every page" may carry the new style flags `uppercase` (text, table) and `headerRow`
  (table): they are style, like bold / italic, so the server's allow-list names them.
- N2: the page-edit table check types the new flags: on / off only (a string "false" would read as
  on in the designer).
"""
from __future__ import annotations

import pytest


def _table_props(**extra) -> dict:
    side = {"color": "#000000", "width_mm": 0.2}
    return {
        "kind": "table",
        "columns": [{"width_mm": 30}],
        "rows": [{"height_mm": 6}],
        "cells": [[{"text": "A", "border": {"top": side}}]],
        **extra,
    }


@pytest.mark.parametrize("key", ["uppercase", "headerRow"])
def test_s3_every_page_accepts_the_new_style_flag(key):
    from app.services.project_spec_sheet_service import _check_apply

    assert _check_apply({"props": {key: True}}) == {"props": {key: True}}


def test_s3_every_page_still_refuses_what_a_layer_says():
    from app.services.error_handler import AppException
    from app.services.project_spec_sheet_service import _check_apply

    with pytest.raises(AppException):
        _check_apply({"props": {"text": "x"}})


@pytest.mark.parametrize("key", ["headerRow", "uppercase"])
@pytest.mark.parametrize("value", [True, False, None])
def test_n2_table_check_accepts_on_off_or_absent(key, value):
    from app.utils.table_layer_check import table_props_problem

    props = _table_props(**({key: value} if value is not None else {}))
    assert table_props_problem(props) is None


@pytest.mark.parametrize("key", ["headerRow", "uppercase"])
@pytest.mark.parametrize("value", ["false", 1, "yes", {}])
def test_n2_table_check_refuses_a_flag_that_is_not_on_or_off(key, value):
    from app.utils.table_layer_check import table_props_problem

    assert table_props_problem(_table_props(**{key: value})) is not None
