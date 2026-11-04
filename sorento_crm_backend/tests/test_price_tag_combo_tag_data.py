"""PRICETAG-COMBO: what a combo line resolves on its tag, and what it costs.

UAC: `documentation/plans/dealer-kit/price-tag-combo-template-fields-acceptance-criteria.md`
(AC-2.1 to AC-2.9).

Written test-FIRST (PRINCIPLES.md Phase 2). The `combo` object, the combo price
columns and the RM 0 part rule do not exist yet; every case is red because the
column, the key or the behaviour is missing, never because of a harness error.

Standard fixture (synthetic): host list 1000, fixed mirror 200, Basin group of
white (300) and black (400), one upgrade part (list 500). With the white basin
picked, today's sum is 1000 + 200 + 300 = 1500.
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests._pg_fixture import blank_session

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)

D = Decimal


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    r9.block_respond(monkeypatch)
    monkeypatch.setattr(
        "app.services.dealer_kit.product_images.resolve_signed_url",
        lambda path, **_kwargs: f"https://signed.example.test/{path.rsplit('/', 1)[-1]}",
    )


@pytest.fixture
def crm():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as session:
        r9.seed_marketer(session)

        def _override_get_db():
            yield session

        async def _override_scope():
            scope = frozenset({r9.SORENTO})
            set_company_scope(session, scope)
            return scope

        principal = {"id": r9.MARKETER_ID, "email": "zzt-ptag-r9-marketer@test.com"}
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
        try:
            with TestClient(app) as client:
                yield client, session
        finally:
            app.dependency_overrides.clear()


def _std(
    db,
    *,
    combo_fields=None,
    white_sell=None,
    black_sell=None,
    upgrade_topup=None,
    with_upgrade=False,
):
    """The standard product chain and combo. Returns a dict.

    New part columns are only passed when a test sets them, so a test that does not
    need a new column does not fail on the fixture.
    """
    host, mirror, white, black, upgrade = seed.basin_combo(db)

    def _option(item, sell):
        spec = {"product": item, "group": "Basin"}
        if sell is not None:
            spec["sell_price"] = sell
        return spec

    parts = [{"product": mirror}, _option(white, white_sell), _option(black, black_sell)]
    if with_upgrade:
        spec = {"product": upgrade, "is_upgrade": True}
        if upgrade_topup is not None:
            spec["topup_amount"] = upgrade_topup
        parts.append(spec)
    cb = seed.combo(db, host, "ZZT 4 in 1", parts=parts, **(combo_fields or {}))
    return {"host": host, "mirror": mirror, "white": white, "black": black, "upgrade": upgrade, "combo": cb}


def _line_parts(s, pick=None):
    """The dealer's parts: the fixed mirror, then the pick (or the Basin group left open)."""
    parts = [{"product_id": s["mirror"].id}]
    if pick is None:
        parts.append({"role": "Basin", "candidates": [s["white"].id, s["black"].id]})
    elif pick is s["upgrade"]:
        parts.append({"product_id": s["upgrade"].id})
    else:
        parts.append({"product_id": pick.id, "role": "Basin"})
    return parts


def _row(db, s, pick=None, **kwargs):
    request = seed.submit_one(db, s["host"], s["combo"], _line_parts(s, pick), **kwargs)
    db.flush()
    return seed.rows(db, request)[0], request


# --------------------------------------------------------------------------- AC-2.1


def test_ac_2_1_a_combo_line_resolves_the_whole_combo_object(db):
    s = _std(
        db,
        combo_fields={"description": "Cabinet, mirror, basin", "free_items": "Tap, waste"},
        white_sell=D("280.00"),
        upgrade_topup=D("100.00"),
        with_upgrade=True,
    )
    row, _request = _row(db, s)
    combo = row["combo"]

    assert set(combo) == {"id", "name", "description", "free_items", "choices", "upgrades"}
    assert combo["id"] == s["combo"].id
    assert combo["name"] == "ZZT 4 in 1"
    assert combo["description"] == "Cabinet, mirror, basin"
    assert combo["free_items"] == "Tap, waste"

    assert [group["role"] for group in combo["choices"]] == ["Basin"]
    options = combo["choices"][0]["options"]
    assert [set(option) for option in options] == [
        {"product_id", "code", "description", "list_price", "sell_price", "picked"}
    ] * 2
    white, black = options
    assert white["product_id"] == s["white"].id
    assert white["code"] == s["white"].product_code
    # The product's description text, else its product name (which equals its code here).
    assert white["description"] == "White basin"
    assert black["description"] == s["black"].product_name == s["black"].product_code
    assert white["list_price"] == D("300.00") and black["list_price"] == D("400.00")
    assert white["sell_price"] == D("280.00"), "the part row's own sell price"
    assert black["sell_price"] is None, "blank stays null"
    assert white["picked"] is False and black["picked"] is False

    assert len(combo["upgrades"]) == 1
    upgrade = combo["upgrades"][0]
    assert set(upgrade) == {"product_id", "code", "description", "topup_amount", "picked"}
    assert upgrade["product_id"] == s["upgrade"].id
    assert upgrade["code"] == s["upgrade"].product_code
    assert upgrade["description"] == "Stone basin"
    assert upgrade["topup_amount"] == D("100.00")
    assert upgrade["picked"] is False
    # Fixed parts are neither a choice nor an upgrade.
    assert s["mirror"].id not in {o["product_id"] for g in combo["choices"] for o in g["options"]}


def test_ac_2_1_a_line_with_no_combo_resolves_combo_null(db):
    host = seed.product(db, "ZZCPLAIN")
    request = seed.submit_one(db, host)
    db.flush()
    row = seed.rows(db, request)[0]
    assert "combo" in row
    assert row["combo"] is None


def test_ac_2_2_picked_follows_the_dealers_line_part(db):
    s = _std(db)
    row, _ = _row(db, s, pick=s["black"])
    options = {o["product_id"]: o for o in row["combo"]["choices"][0]["options"]}
    assert options[s["black"].id]["picked"] is True
    assert options[s["white"].id]["picked"] is False


def test_ac_2_2_picked_follows_the_tags_choices_too(db):
    s = _std(db)
    row, request = _row(db, s)
    tag = request.lines[0].tags[0]
    tag.choices = {"Basin": s["white"].id}
    db.flush()
    db.expire_all()
    (row,) = [r for r in seed.rows(db, request) if r["tag_id"] == tag.id]
    options = {o["product_id"]: o for o in row["combo"]["choices"][0]["options"]}
    assert options[s["white"].id]["picked"] is True
    assert options[s["black"].id]["picked"] is False


def test_ac_2_2_a_picked_upgrade_is_marked_picked(db):
    s = _std(db, upgrade_topup=D("100.00"), with_upgrade=True)
    row, _ = _row(db, s, pick=s["upgrade"])
    (upgrade,) = row["combo"]["upgrades"]
    assert upgrade["picked"] is True


# --------------------------------------------------------------------------- AC-2.3


def test_ac_2_3_the_lines_own_accessories_text_wins(db):
    s = _std(db, combo_fields={"free_items": "Combo tap"})
    row, _ = _row(db, s, pick=s["white"], included_accessories="Line tap")
    assert row["included_accessories"] == "Line tap"


def test_ac_2_3_a_blank_line_text_falls_back_to_the_combos_free_items(db):
    s = _std(db, combo_fields={"free_items": "Combo tap, waste"})
    row, _ = _row(db, s, pick=s["white"])
    assert row["included_accessories"] == "Combo tap, waste"


def test_ac_2_3_no_free_items_and_no_line_text_stays_empty(db):
    s = _std(db)
    row, _ = _row(db, s, pick=s["white"])
    assert row["included_accessories"] == ""


# --------------------------------------------------------------------------- AC-2.4


def test_ac_2_4_with_no_combo_price_nothing_prints_never_the_sum(db):
    # PRICETAG-COMBO-RENDER K8: the part sum is never used on a combo line.
    s = _std(db)
    row, _ = _row(db, s, pick=s["white"])
    assert row["list_price"] is None
    assert row["sell_price"] is None


def test_ac_2_4_the_combo_list_price_replaces_the_summed_list_price_only(db):
    s = _std(db, combo_fields={"list_price": D("2000.00")})
    row, _ = _row(db, s, pick=s["white"])
    assert row["list_price"] == D("2000.00")
    assert row["sell_price"] is None, "no sell price set: nothing, never the sum"


def test_ac_2_4_the_combo_sell_price_replaces_the_summed_sell_price(db):
    s = _std(db, combo_fields={"sell_price": D("1800.00")})
    row, _ = _row(db, s, pick=s["white"])
    assert row["sell_price"] == D("1800.00")
    assert row["list_price"] is None, "no list price set: nothing, never the sum"


def test_ac_2_4_the_picked_options_sell_price_beats_the_combo_sell_price(db):
    s = _std(db, combo_fields={"sell_price": D("1800.00")}, white_sell=D("1700.00"))
    row, _ = _row(db, s, pick=s["white"])
    assert row["sell_price"] == D("1700.00")


def test_ac_2_4_a_picked_option_with_no_sell_price_falls_to_the_combo_sell_price(db):
    s = _std(db, combo_fields={"sell_price": D("1800.00")}, white_sell=D("1700.00"))
    row, _ = _row(db, s, pick=s["black"])
    assert row["sell_price"] == D("1800.00")


def test_ac_2_4_a_picked_upgrade_adds_its_topup_to_the_combo_price(db):
    s = _std(db, combo_fields={"sell_price": D("1800.00")}, upgrade_topup=D("100.00"), with_upgrade=True)
    row, _ = _row(db, s, pick=s["upgrade"])
    assert row["sell_price"] == D("1900.00")


def test_ac_2_4_a_picked_upgrade_with_a_blank_topup_prints_the_price_alone(db):
    s = _std(db, combo_fields={"sell_price": D("1800.00")}, with_upgrade=True)
    row, _ = _row(db, s, pick=s["upgrade"])
    assert row["sell_price"] == D("1800.00")


def test_ac_2_4_a_picked_upgrade_with_a_zero_topup_prints_the_price_alone(db):
    s = _std(db, combo_fields={"sell_price": D("1800.00")}, upgrade_topup=D("0.00"), with_upgrade=True)
    row, _ = _row(db, s, pick=s["upgrade"])
    assert row["sell_price"] == D("1800.00")


def test_ac_2_4_a_picked_upgrade_on_a_combo_with_no_sell_price_is_todays_sum(db):
    s = _std(db, upgrade_topup=D("100.00"), with_upgrade=True)
    row, _ = _row(db, s, pick=s["upgrade"])
    # No stored price to add the top-up to: nothing prints (never the part sum).
    assert row["sell_price"] is None


def test_ac_2_4_the_line_manual_price_beats_the_combo_price(db):
    s = _std(db, combo_fields={"sell_price": D("1800.00")}, white_sell=D("1700.00"))
    row, _ = _row(db, s, pick=s["white"], manual_sell_price="1234.00", price_mode="selling")
    assert row["sell_price"] == D("1234.00")


def test_ac_2_4_the_tag_override_beats_the_manual_price_and_the_combo_price(db):
    s = _std(db, combo_fields={"sell_price": D("1800.00")})
    row, request = _row(db, s, pick=s["white"], manual_sell_price="1234.00", price_mode="selling")
    tag = request.lines[0].tags[0]
    tag.marketing_price_override = D("999.00")
    tag.marketing_override_reason = "ZZT roadshow"
    db.flush()
    (row,) = [r for r in seed.rows(db, request) if r["tag_id"] == tag.id]
    assert row["sell_price"] == D("999.00")


# --------------------------------------------------------------------------- AC-2.5


def test_ac_2_5_nothing_picked_with_an_option_price_and_no_combo_price_is_null(db):
    s = _std(db, white_sell=D("1700.00"))
    row, _ = _row(db, s)
    assert row["sell_price"] is None, "each option prints its own price instead"


# --------------------------------------------------------------------------- AC-2.6


def _agreement_setup(db):
    s = _std(
        db,
        combo_fields={"list_price": D("2000.00"), "sell_price": D("1800.00")},
        white_sell=D("1700.00"),
        upgrade_topup=D("100.00"),
        with_upgrade=True,
    )
    return s


def _pricing_line(s, part_ids):
    return {
        "key": "L1",
        "product_id": s["host"].id,
        "part_product_ids": part_ids,
        "candidate_product_ids": [],
        "combo_id": s["combo"].id,
    }


def test_ac_2_6_tag_data_and_line_pricing_answer_the_same_option_price(db):
    from app.services.dealer_kit import tag_data_service
    from app.services.dealer_kit.pricing import line_pricing

    s = _agreement_setup(db)
    row, _ = _row(db, s, pick=s["white"])
    (priced,) = line_pricing(
        db,
        lines=[_pricing_line(s, [s["mirror"].id, s["white"].id])],
        viewer=tag_data_service.staff_viewer(),
    )
    assert row["sell_price"] == D("1700.00")
    assert D(str(priced["sell_price"])) == row["sell_price"]
    assert D(str(priced["list_price"])) == row["list_price"] == D("2000.00")


def test_ac_2_6_tag_data_and_line_pricing_answer_the_same_upgrade_price(db):
    from app.services.dealer_kit import tag_data_service
    from app.services.dealer_kit.pricing import line_pricing

    s = _agreement_setup(db)
    row, _ = _row(db, s, pick=s["upgrade"])
    (priced,) = line_pricing(
        db,
        lines=[_pricing_line(s, [s["mirror"].id, s["upgrade"].id])],
        viewer=tag_data_service.staff_viewer(),
    )
    assert row["sell_price"] == D("1900.00")
    assert D(str(priced["sell_price"])) == D("1900.00")


def test_ac_2_6_the_crm_line_pricing_route_answers_the_same_combo_price(crm):
    client, db = crm
    s = _agreement_setup(db)
    row, _ = _row(db, s, pick=s["white"])
    db.commit()

    response = client.post(
        "/api/v1/dealer-kit/price-tag-requests/line-pricing",
        json={
            "lines": [
                {
                    "key": "L1",
                    "product_id": s["host"].id,
                    "part_product_ids": [s["mirror"].id, s["white"].id],
                    "candidate_product_ids": [],
                    "combo_id": s["combo"].id,
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    (priced,) = response.json()
    assert D(str(priced["sell_price"])) == row["sell_price"] == D("1700.00")
    assert D(str(priced["list_price"])) == D("2000.00")


def test_ac_2_6_a_line_without_combo_id_prices_as_today(db):
    """Pinned on purpose: passes today and must keep passing."""
    from app.services.dealer_kit import tag_data_service
    from app.services.dealer_kit.pricing import line_pricing

    s = _std(db)
    (priced,) = line_pricing(
        db,
        lines=[
            {
                "key": "L1",
                "product_id": s["host"].id,
                "part_product_ids": [s["mirror"].id, s["white"].id],
                "candidate_product_ids": [],
            }
        ],
        viewer=tag_data_service.staff_viewer(),
    )
    assert D(str(priced["sell_price"])) == D("1500.00")
    assert D(str(priced["list_price"])) == D("1500.00")


# --------------------------------------------------------------------------- AC-2.7


# --------------------------------------------------------------------------- AC-2.8


def _designing(db, s):
    """A designing request on a combo line with only the fixed mirror, pinned, with a design."""
    from app.services.price_tag_request_service import PriceTagRequestService

    request = PriceTagRequestService.create_request(
        db,
        contact_id=r9.seed_portal_contact(db),
        company_id=r9.SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "lines": [
                {
                    "line_type": "product",
                    "product_id": s["host"].id,
                    "combo_id": s["combo"].id,
                    "quantity": 1,
                    "parts": [{"product_id": s["mirror"].id}],
                }
            ],
        },
    )
    request.portal_draft_at = None
    request.assigned_to_id = r9.MARKETER_ID
    request.print_by = "office"
    request.status = "new"
    db.flush()
    db.commit()
    PriceTagRequestService.transition_status(db, request.id, "designing", user_id=r9.MARKETER_ID)
    db.commit()
    r9.attach_design(db, request)
    return request


def _fixed_combo(db):
    host = seed.product(db, "ZZCHOST", list_price="1000.00")
    mirror = seed.product(db, "ZZCMIR", list_price="200.00")
    cb = seed.combo(
        db,
        host,
        "ZZT pair",
        parts=[{"product": mirror}],
        description="Old text",
        free_items="Old free",
        list_price=D("2000.00"),
        sell_price=D("1500.00"),
    )
    return {"host": host, "mirror": mirror, "combo": cb}


def _pinned_tag(db, request):
    db.expire_all()
    return r9.first_tag(request)


def test_ac_2_8_a_designing_tag_picks_up_changed_combo_text_and_price(crm):
    client, db = crm
    s = _fixed_combo(db)
    request = _designing(db, s)
    tag = _pinned_tag(db, request)
    assert tag.pinned_tag_data["combo"]["description"] == "Old text"

    s["combo"].description = "New text"
    s["combo"].free_items = "New free"
    s["combo"].sell_price = D("1400.00")
    db.commit()

    response = client.get(f"/api/v1/dealer-kit/price-tag-requests/{request.id}/data-changes")
    assert response.status_code == 200, response.text

    tag = _pinned_tag(db, request)
    assert tag.data_updated_at is not None
    assert tag.pinned_tag_data["combo"]["description"] == "New text"
    assert tag.pinned_tag_data["combo"]["free_items"] == "New free"
    assert D(str(tag.pinned_tag_data["sell_price"])) == D("1400.00")
    labels = " ".join(str(change) for change in (tag.data_update_changes or [])).lower()
    assert "description" in labels, "the change note names the combo description"


def test_ac_2_8_an_approved_pinned_tag_keeps_its_text_and_figures(crm):
    client, db = crm
    s = _fixed_combo(db)
    request = _designing(db, s)
    tag = _pinned_tag(db, request)
    old_sell = D(str(tag.pinned_tag_data["sell_price"]))
    request.status = "proof_ready"
    db.commit()

    s["combo"].description = "New text"
    s["combo"].free_items = "New free"
    s["combo"].sell_price = D("1400.00")
    db.commit()

    client.get(f"/api/v1/dealer-kit/price-tag-requests/{request.id}/data-changes")
    db.expire_all()
    (row,) = seed.rows(db, request)
    assert row["combo"]["description"] == "Old text"
    assert row["combo"]["free_items"] == "Old free"
    assert row["sell_price"] == old_sell == D("1500.00")
    assert row["included_accessories"] == "Old free", "a blank line text reads the pinned free items"
    assert _pinned_tag(db, request).data_updated_at is None


def test_ac_2_8_a_payload_pinned_before_this_lane_renders_combo_null(crm):
    _client, db = crm
    s = _fixed_combo(db)
    request = _designing(db, s)
    tag = _pinned_tag(db, request)
    old = dict(tag.pinned_tag_data)
    old.pop("combo")
    tag.pinned_tag_data = old
    request.status = "proof_ready"
    db.commit()

    (row,) = seed.rows(db, request)
    assert "combo" in row
    assert row["combo"] is None


# --------------------------------------------------------------------------- AC-2.9


def test_ac_2_9_the_export_payload_carries_the_combo(crm):
    from app.services.dealer_kit import tag_sheet_export_service

    _client, db = crm
    s = _fixed_combo(db)
    request = _designing(db, s)
    page = request.page_id
    from app.models.dealer_kit import Page, PageVersion

    version = db.query(PageVersion).filter(PageVersion.page_id == page).first()
    payload = tag_sheet_export_service._resolved_payload(
        db,
        {
            "page_id": page,
            "version_id": None,
            "version": version.version,
            "doc": version.doc,
            "request": request,
            "page": db.query(Page).filter(Page.id == page).one(),
        },
    )
    tag = r9.first_tag(request)
    combo = payload["resolvedData"][tag.id]["combo"]
    assert combo is not None, "ResolvedLineData must declare `combo` or the PDF drops it"
    assert combo["name"] == "ZZT pair"
    assert combo["description"] == "Old text"
    assert combo["free_items"] == "Old free"


# --------------------------------------------------------------------------- sell above list


def test_a_combo_sell_price_above_the_list_price_still_prints_in_selling_mode(db):
    """A real case: a sink with an included tap lists at 1,090 and sells at 1,099."""
    from app.services.dealer_kit import tag_data_service
    from app.services.dealer_kit.pricing import line_pricing

    s = _std(db, combo_fields={"list_price": D("1090.00"), "sell_price": D("1099.00")})
    row, _ = _row(db, s, pick=s["white"], price_mode="selling")
    assert row["list_price"] == D("1090.00")
    assert row["sell_price"] == D("1099.00")
    assert row["show_promo_price"] is True, "the combo's sell price is never dropped for being above list"
    assert row["sell_price_basis"] != "list"

    (priced,) = line_pricing(
        db,
        lines=[_pricing_line(s, [s["mirror"].id, s["white"].id])],
        viewer=tag_data_service.staff_viewer(),
        auto_pick=False,
    )
    assert D(str(priced["sell_price"])) == D("1099.00")
    assert priced["sell_price_basis"] != "list"


# --------------------------------------------------------------------------- review round


def test_ac_2_8_a_description_only_edit_reaches_a_designing_tag_with_its_change_note(crm):
    client, db = crm
    s = _fixed_combo(db)
    request = _designing(db, s)
    s["combo"].description = "Only the description moved"
    db.commit()

    assert client.get(f"/api/v1/dealer-kit/price-tag-requests/{request.id}/data-changes").status_code == 200
    tag = _pinned_tag(db, request)
    assert tag.data_updated_at is not None
    assert tag.pinned_tag_data["combo"]["description"] == "Only the description moved"
    labels = " ".join(str(change) for change in (tag.data_update_changes or [])).lower()
    assert "combo description" in labels


def test_ac_2_7_a_promotion_option_on_a_combo_line_is_the_combos_figure_never_a_sum(db):
    from app.services.dealer_kit import tag_data_service
    from app.services.dealer_kit.pricing import line_pricing

    viewer = tag_data_service.staff_viewer()
    promo_lines = lambda s: [(s["host"], "800.00"), (s["mirror"], "0.00")]  # noqa: E731

    s = _std(db, combo_fields={"sell_price": D("1800.00")})
    promo = seed.promotion(db, promo_lines(s))
    line = {**_pricing_line(s, [s["mirror"].id, s["white"].id]), "promotion_id": promo.id}
    (priced,) = line_pricing(db, lines=[line], viewer=viewer, auto_pick=False)
    assert [o["sell_price"] for o in priced["promotion_options"]] == [D("1800.00")]
    assert D(str(priced["sell_price"])) == D("1800.00")

    # No stored combo price: the option has no figure either (K8), and nothing is summed.
    s2 = _std(db)
    promo2 = seed.promotion(db, promo_lines(s2))
    line2 = {**_pricing_line(s2, [s2["mirror"].id, s2["white"].id]), "promotion_id": promo2.id}
    (priced2,) = line_pricing(db, lines=[line2], viewer=viewer, auto_pick=False)
    assert [o["sell_price"] for o in priced2["promotion_options"]] == [None]
    assert priced2["sell_price"] is None

    # Without the combo the same promotion still sums per part, as before.
    plain = {k: v for k, v in line2.items() if k != "combo_id"}
    (unpriced,) = line_pricing(db, lines=[plain], viewer=viewer, auto_pick=False)
    assert D(str(unpriced["sell_price"])) == D("1300.00")


def test_a_no_combo_row_hashes_as_it_did_before_the_combo_key_existed():
    from app.services.dealer_kit.tag_data_service import data_hash

    row = {"code": "ZZ1", "name": "ZZ1", "list_price": 10.0, "sell_price": None, "images": [], "parts": []}
    assert data_hash({**row, "combo": None}) == data_hash(row)
    assert data_hash({**row, "combo": {"id": "c", "name": "n"}}) != data_hash(row)


def test_ac_2_5_is_judged_per_group(db):
    from app.services.dealer_kit.pricing import combo_prices

    host = seed.product(db, "ZZGHOST", list_price="1000.00")
    a1 = seed.product(db, "ZZGA1")
    a2 = seed.product(db, "ZZGA2")
    b1 = seed.product(db, "ZZGB1")
    b2 = seed.product(db, "ZZGB2")
    cb = seed.combo(
        db,
        host,
        "ZZT two groups",
        parts=[
            {"product": a1, "group": "Basin", "sell_price": D("100.00")},
            {"product": a2, "group": "Basin"},
            {"product": b1, "group": "Tap", "sell_price": D("40.00")},
            {"product": b2, "group": "Tap"},
        ],
    )
    # Basin picked with a price, Tap still open and priced: blank, each Tap prints its own.
    assert combo_prices(cb, {a1.id})[1:] == (None, True)
    # Both picked: the first picked option that has a price.
    assert combo_prices(cb, {a1.id, b1.id})[1:] == (D("100.00"), True)
    # Only the unpriced Basin option picked, Tap's pick is priced: Tap's price counts.
    assert combo_prices(cb, {a2.id, b1.id})[1:] == (D("40.00"), True)
    # Both groups picked with no price on either picked option: today's sum.
    assert combo_prices(cb, {a2.id, b2.id})[1:] == (None, False)


def test_the_request_design_route_answers_200_with_the_combo_on_a_combo_line(crm):
    """The Design card swallows any error as "No design yet"; this pins that a combo line does
    not make the route throw, and that the combo reaches the lines it answers."""
    client, db = crm
    s = _fixed_combo(db)
    request = _designing(db, s)
    response = client.get(f"/api/v1/dealer-kit/price-tag-requests/{request.id}/design")
    assert response.status_code == 200, response.text
    (line,) = response.json()["lines"]
    assert line["combo"]["name"] == "ZZT pair"
