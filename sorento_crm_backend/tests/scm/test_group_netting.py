"""`app.services.scm.group_netting` - the one reader of availability (ladder v4).

`PLAN-scm-cs-planning-uat.md` section 1d, ruled 26 August 2026: the unit of availability is
the OWNERSHIP GROUP, never one warehouse. Every number the ladder, the cell popover, the
order-inquiry link walk and (S12) the WhatsApp stock answer draw on comes from here, so this
file pins the arithmetic itself rather than any one of their readings of it.

Two halves, and they are tested apart on purpose. The CLASS is pure - it is handed a triple
per `(product, warehouse)` and nothing else - so its cases are plain data and run in
milliseconds. The db constructor at the bottom is the half that reads, and it gets its own
Postgres test (`tests/_pg_fixture.py::blank_session`, per PRINCIPLES.md - never sqlite).
"""
from __future__ import annotations

from decimal import Decimal

from app.services.scm.group_netting import (
    GroupNetting,
    group_of_warehouse_code,
    netting_for_products,
)

from .._pg_fixture import blank_session

PRODUCT = "prod-1"

#: `B2155-NL-BLUE` as the captain measured it on 26 August 2026, which is the case the whole
#: ruling came from: BRW-IB holds 5290 against 27,804 owed, MWH-IB holds 7000 against
#: nothing, and read warehouse by warehouse the second looks like 7000 free to promise.
IB_WORLD = {
    (PRODUCT, "w-brw-ib"): {"on_hand": Decimal("5290"), "so_qty": Decimal("27804"), "spo_qty": Decimal("0")},
    (PRODUCT, "w-mwh-ib"): {"on_hand": Decimal("7000"), "so_qty": Decimal("0"), "spo_qty": Decimal("0")},
    (PRODUCT, "w-brw"): {"on_hand": Decimal("1"), "so_qty": Decimal("10"), "spo_qty": Decimal("0")},
}

CODES = {
    "w-brw-ib": "BRW-IB",
    "w-mwh-ib": "MWH-IB",
    "w-rsw-ib": "RSW-IB",
    "w-brw-bb": "BRW-BB",
    "w-brw": "BRW",
    "w-dc1": "DC1",
    "w-mwh": "MWH",
    "w-rsw": "RSW",
    "w-wh3": "WH3",
}

POOLS = {"w-brw", "w-dc1", "w-mwh", "w-rsw", "w-wh3"}


def _netting(triples=None, codes=None):
    return GroupNetting(
        triples=triples if triples is not None else IB_WORLD,
        warehouse_codes=codes if codes is not None else CODES,
        pool_warehouse_ids=POOLS,
    )


# --------------------------------------------------------------------- the group


def test_the_group_nets_over_every_one_of_its_locations():
    """AC-L7's own number: 5290 - 27804 + 7000 - 0 = -15514."""
    position = _netting().group_net(PRODUCT, "IB")

    assert position.net == Decimal("-15514")
    assert position.offer == Decimal("0")


def test_a_location_with_no_triple_counts_as_three_zeroes_and_not_as_absent():
    """RSW-IB has no `stock` row and no open line, and it is still a member of the group.

    Counting it as absent and counting it as zero give the same net here; what they do not
    give the same is the EVIDENCE, and a group listing that silently drops its empty members
    cannot be checked against the warehouse list.
    """
    position = _netting().group_net(PRODUCT, "IB")

    assert [entry.location for entry in position.by_location] == [
        "BRW-IB",
        "MWH-IB",
        "RSW-IB",
    ]
    assert position.by_location[2].net == Decimal("0")


def test_a_warehouse_outside_the_group_takes_no_part_in_it():
    """`BRW-BB` and the pools are not IB stock, however much they hold."""
    triples = dict(IB_WORLD)
    triples[(PRODUCT, "w-brw-bb")] = {
        "on_hand": Decimal("9999"), "so_qty": Decimal("0"), "spo_qty": Decimal("0"),
    }

    assert _netting(triples).group_net(PRODUCT, "IB").net == Decimal("-15514")


def test_an_inactive_warehouse_is_not_in_the_group_because_it_is_not_in_the_codes():
    """The span IS the active warehouse list the caller hands over.

    Stated as a test because it is the whole reason this class takes its codes as an
    argument: "which warehouses exist" is a decision made once, by the reader that queried
    them, and a second opinion here would be a second answer.
    """
    codes = {k: v for k, v in CODES.items() if k != "w-mwh-ib"}

    assert _netting(codes=codes).group_net(PRODUCT, "IB").net == Decimal("-22514")


def test_an_spo_is_inside_the_net_and_not_beside_it():
    """Section 1d rung 1: an SPO to BRW-IB is owed to the IB backlog first.

    SRTWC7405-SC, measured: 2 + 330 on hand, 110 arriving, 2335 owed - which is -1893 with
    the SPO counted, so the SPO covers no line of the group. Counting it beside the net
    instead would promise the same 110 twice.
    """
    triples = {
        (PRODUCT, "w-brw-ib"): {
            "on_hand": Decimal("2"), "so_qty": Decimal("2335"), "spo_qty": Decimal("110"),
        },
        (PRODUCT, "w-mwh-ib"): {
            "on_hand": Decimal("330"), "so_qty": Decimal("0"), "spo_qty": Decimal("0"),
        },
    }

    assert _netting(triples).group_net(PRODUCT, "IB").net == Decimal("-1893")


def test_an_unknown_group_nets_zero_over_no_locations():
    position = _netting().group_net(PRODUCT, "ZZ")

    assert position.net == Decimal("0")
    assert position.by_location == ()


# --------------------------------------------------------------------- the pools


def test_the_five_site_pools_net_as_one_pile():
    """AC-L8: `BRW -103` beside `DC1 +1` is -102, and the 1 is not available to anybody."""
    triples = {
        (PRODUCT, "w-brw"): {"on_hand": Decimal("0"), "so_qty": Decimal("103"), "spo_qty": Decimal("0")},
        (PRODUCT, "w-dc1"): {"on_hand": Decimal("1"), "so_qty": Decimal("0"), "spo_qty": Decimal("0")},
    }
    position = _netting(triples).pools_net(PRODUCT)

    assert position.net == Decimal("-102")
    assert position.offer == Decimal("0")
    assert len(position.by_location) == 5


def test_a_group_warehouse_is_never_counted_in_the_pool_pile():
    assert _netting().pools_net(PRODUCT).net == Decimal("-9")


# --------------------------------------------------------------- the donor group


def test_the_donor_group_is_the_same_arithmetic_under_the_rung_4_name():
    """A single warehouse's on hand means nothing if its group nets negative."""
    netting = _netting()

    assert netting.donor_group_net(PRODUCT, "IB").net == netting.group_net(
        PRODUCT, "IB"
    ).net


# ------------------------------------------------------------------- addressing


def test_it_knows_a_pool_from_a_group_member():
    netting = _netting()

    assert netting.is_pool("w-brw") is True
    assert netting.is_pool("w-brw-ib") is False
    assert netting.group_of("w-brw-ib") == "IB"
    assert netting.group_of("w-brw") is None


def test_the_suffix_rule_is_the_shared_one():
    assert group_of_warehouse_code("BRW-IB") == "IB"
    assert group_of_warehouse_code("BRW") is None


# ------------------------------------------------------------- the db constructor


def test_netting_for_products_reads_the_same_three_figures_off_postgres():
    """The S12 entry point: no board, no supply service, one call.

    Seeds its own chain rather than reading whatever the database happens to hold, per this
    repo's CI-is-empty lesson.
    """
    from tests.test_so_supply_confirmation import (
        _core_line, _core_so, _product, _sorento, _stock, _warehouse,
    )

    with blank_session() as db:
        company_id = _sorento(db)
        product = _product(db)
        own = _warehouse(db, "ZZTNETBRW-QQ")
        sibling = _warehouse(db, "ZZTNETMWH-QQ")
        _stock(db, product, own, on_hand=5)
        _stock(db, product, sibling, on_hand=70)
        core_so = _core_so(db, company_id)
        _core_line(db, core_so, product, own, qty_ordered="200")
        db.commit()

        position = netting_for_products(db, [str(product.id)]).group_net(
            str(product.id), "QQ"
        )

    assert position.net == Decimal("-125")
    assert {entry.location for entry in position.by_location} == {
        "ZZTNETBRW-QQ",
        "ZZTNETMWH-QQ",
    }
