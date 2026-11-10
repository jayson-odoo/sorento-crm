"""RED tests B6: costing settings and category transport rules (PRODUCT-COSTING, Phase 2).
AC-ST-01, AC-ST-02, AC-LC-06, AC-AX-01.

Routes (contract 4.6), all under /api/v1/master-data/costing:
    GET  /settings                      -> {sst_factor, default_method}; defaults 1.1 / "primary"
    PUT  /settings          (manage)    same body; sst_factor > 0; default_method in
                                        (primary, average, last_po) -- "selected" is 422
    GET  /category-rules                -> {"data": [{category_id, category_name, mode, value}]},
                                        every category; mode/value null without a rule
    PUT  /category-rules/{category_id}  {mode, value}; both null clears (manage)
Audit: `costing_settings` rows (entity_id = the row id) and `costing_category_rules`
(entity_id = category_id), actions INSERT / UPDATE / DELETE with old_values / new_values.
A write answers 200 with the new settings / the rule row (`{category_id, mode, value}`).
"""
from __future__ import annotations

import pytest

from tests.support.costing_env import COST_VIEW, MANAGE, costing_env  # noqa: F401


def _by_cat(response):
    assert response.status_code == 200, response.text
    return {r["category_id"]: r for r in response.json()["data"]}


# ------------------------------------------------------------------ AC-ST-01 settings


def test_ac_st_01_a_read_with_no_row_returns_the_defaults_and_writes_nothing(costing_env):
    from app.models.costing import CostingSettings

    e = costing_env
    e.as_user(e.viewer())
    r = e.get("/settings")
    assert r.status_code == 200, r.text
    assert r.json() == {"sst_factor": 1.1, "default_method": "primary"}
    assert e.db.query(CostingSettings).count() == 0


def test_ac_st_01_put_creates_the_row_then_updates_it_and_both_are_returned(costing_env):
    from app.models.costing import CostingSettings

    e = costing_env
    e.as_user(e.manager())
    r = e.put("/settings", {"sst_factor": 1.06, "default_method": "average"})
    assert r.status_code == 200, r.text
    assert r.json() == {"sst_factor": 1.06, "default_method": "average"}
    assert e.get("/settings").json() == {"sst_factor": 1.06, "default_method": "average"}
    assert e.db.query(CostingSettings).count() == 1

    e.put("/settings", {"sst_factor": 1.1, "default_method": "last_po"})
    assert e.db.query(CostingSettings).count() == 1  # one row per company
    assert e.get("/settings").json() == {"sst_factor": 1.1, "default_method": "last_po"}


def test_ac_st_01_changes_are_audited_with_old_and_new(costing_env):
    e = costing_env
    e.as_user(e.manager())
    assert e.put("/settings", {"sst_factor": 1.06, "default_method": "primary"}).status_code == 200
    assert e.put("/settings", {"sst_factor": 1.08, "default_method": "average"}).status_code == 200

    from app.models.costing import CostingSettings

    row = e.db.query(CostingSettings).one()
    audits = e.audit_rows("costing_settings", row.id)
    assert audits[0].action == "INSERT"
    assert audits[-1].action == "UPDATE"
    assert float(audits[-1].old_values["sst_factor"]) == pytest.approx(1.06)
    assert float(audits[-1].new_values["sst_factor"]) == pytest.approx(1.08)
    assert audits[-1].old_values["default_method"] == "primary"
    assert audits[-1].new_values["default_method"] == "average"
    assert audits[-1].user_id == e.principal["id"]


@pytest.mark.parametrize("body", [
    {"sst_factor": 0, "default_method": "primary"},
    {"sst_factor": -1.1, "default_method": "primary"},
    {"sst_factor": 1.1, "default_method": "bogus"},
    {"sst_factor": 1.1},
    {"default_method": "primary"},
])
def test_ac_st_01_invalid_settings_are_422_and_nothing_is_written(costing_env, body):
    from app.models.costing import CostingSettings

    e = costing_env
    e.as_user(e.manager())
    assert e.put("/settings", body).status_code == 422
    assert e.db.query(CostingSettings).count() == 0


def test_ac_lc_06_selected_supplier_is_not_a_company_default(costing_env):
    from app.models.costing import CostingSettings

    e = costing_env
    e.as_user(e.manager())
    r = e.put("/settings", {"sst_factor": 1.1, "default_method": "selected"})
    assert r.status_code == 422, r.text
    assert e.db.query(CostingSettings).count() == 0


def test_ac_ax_01_settings_read_needs_cost_view_and_write_needs_manage_and_cost_view(costing_env):
    e = costing_env
    body = {"sst_factor": 1.1, "default_method": "primary"}
    e.as_user(e.user())
    assert e.get("/settings").status_code == 403
    assert e.get("/category-rules").status_code == 403

    e.as_user(e.viewer())
    assert e.get("/settings").status_code == 200
    assert e.put("/settings", body).status_code == 403  # view alone cannot write

    e.as_user(e.user(MANAGE))
    assert e.put("/settings", body).status_code == 403  # manage without cost view cannot either

    e.as_user(e.manager())
    assert e.put("/settings", body).status_code == 200


# ------------------------------------------------------------------ AC-ST-02 category rules


def test_ac_st_02_category_rules_lists_every_category_with_null_when_no_rule(costing_env):
    e = costing_env
    ceramics = e.category("Ceramics", rule=("add", 8))
    taps = e.category("Taps", rule=("multiply", 1.07))
    bare = e.category("Unruled")
    e.db.commit()
    e.as_user(e.viewer())

    got = _by_cat(e.get("/category-rules"))
    assert got[ceramics.id]["category_name"] == "Ceramics"
    assert (got[ceramics.id]["mode"], got[ceramics.id]["value"]) == ("add", pytest.approx(8))
    assert (got[taps.id]["mode"], got[taps.id]["value"]) == ("multiply", pytest.approx(1.07))
    assert got[bare.id]["mode"] is None and got[bare.id]["value"] is None


def test_ac_st_02_put_sets_changes_and_clears_a_rule(costing_env):
    from app.models.costing import CostingCategoryRule

    e = costing_env
    cat = e.category("Sinks")
    e.db.commit()
    e.as_user(e.manager())

    r = e.put(f"/category-rules/{cat.id}", {"mode": "multiply", "value": 1.1})
    assert r.status_code == 200, r.text
    assert _by_cat(e.get("/category-rules"))[cat.id]["mode"] == "multiply"

    e.put(f"/category-rules/{cat.id}", {"mode": "add", "value": 8})
    got = _by_cat(e.get("/category-rules"))[cat.id]
    assert (got["mode"], got["value"]) == ("add", pytest.approx(8))
    assert e.db.query(CostingCategoryRule).filter_by(category_id=cat.id).count() == 1

    cleared = e.put(f"/category-rules/{cat.id}", {"mode": None, "value": None})
    assert cleared.status_code == 200, cleared.text
    assert e.db.query(CostingCategoryRule).filter_by(category_id=cat.id).count() == 0  # no row = no rule
    assert _by_cat(e.get("/category-rules"))[cat.id]["mode"] is None


@pytest.mark.parametrize("body", [
    {"mode": "divide", "value": 2},
    {"mode": "add", "value": 0},
    {"mode": "multiply", "value": -1.07},
    {"mode": "add", "value": None},
    {"mode": None, "value": 8},
])
def test_ac_st_02_invalid_rules_are_422(costing_env, body):
    from app.models.costing import CostingCategoryRule

    e = costing_env
    cat = e.category("Bad")
    e.db.commit()
    e.as_user(e.manager())
    assert e.put(f"/category-rules/{cat.id}", body).status_code == 422
    assert e.db.query(CostingCategoryRule).filter_by(category_id=cat.id).count() == 0


def test_ac_st_02_unknown_category_is_404(costing_env):
    import uuid

    e = costing_env
    cat = e.category("Real")
    e.db.commit()
    e.as_user(e.manager())
    # a real category is accepted (so a 404 below is about the id, not a missing route)
    assert e.put(f"/category-rules/{cat.id}", {"mode": "add", "value": 8}).status_code == 200
    r = e.put(f"/category-rules/{uuid.uuid4()}", {"mode": "add", "value": 8})
    assert r.status_code == 404, r.text


def test_ac_st_02_rule_changes_are_audited(costing_env):
    e = costing_env
    cat = e.category("Audited")
    e.db.commit()
    e.as_user(e.manager())
    e.put(f"/category-rules/{cat.id}", {"mode": "add", "value": 8})
    e.put(f"/category-rules/{cat.id}", {"mode": "multiply", "value": 1.07})
    e.put(f"/category-rules/{cat.id}", {"mode": None, "value": None})
    actions = [a.action for a in e.audit_rows("costing_category_rules", cat.id)]
    assert actions == ["INSERT", "UPDATE", "DELETE"]


def test_ac_st_02_rule_writes_need_manage_and_cost_view(costing_env):
    e = costing_env
    cat = e.category("Gated")
    e.db.commit()
    body = {"mode": "add", "value": 8}
    for principal in (e.viewer(), e.user(MANAGE), e.user()):
        e.as_user(principal)
        assert e.put(f"/category-rules/{cat.id}", body).status_code == 403
    e.as_user(e.manager())
    assert e.put(f"/category-rules/{cat.id}", body).status_code == 200


def test_ac_st_01_a_new_sst_flows_into_the_rows(costing_env):
    """The settings write is the only way SST moves; /rows must use it (landing 33.875 at 1.2)."""
    e = costing_env
    w = e.workbook()
    e.as_user(e.manager())
    assert e.put("/settings", {"sst_factor": 1.2, "default_method": "primary"}).status_code == 200
    row = e.row_of(e.rows(as_of="2026-11-11"), "CGB9032B")
    assert row["sst_factor"] == pytest.approx(1.2)
    assert row["landing"] == pytest.approx(34.5 * 0.625 * 1.2 + 8, abs=1e-6)
