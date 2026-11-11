"""COST-ACCESS-UNIFIED: one cost rule for contacts, the linked user's `products.cost.view`.

UAC `documentation/plans/procurement/cost-access-unified-11nov-acceptance-criteria.md`.
Red tests written before the implementation. A contact sees cost iff its linked user
(`users.respond_contact_id`) is ACTIVE and holds `products.cost.view`; the stored
`contact_field_reveals` row for `purchase_orders.cost` no longer decides anything.

This file holds the service-level ACs: AC-1, AC-2, AC-6 (service), AC-9. The rest sit beside the
suites they update: AC-7 in `test_contact_bulk_copy_access.py`, AC-8 in
`test_contacts_access_filters.py`, AC-3/AC-4/AC-5 and the AC-6 API in `tests/chatbot/`
(the import boundary keeps `app.services.chatbot` imports under that directory).

Postgres only (`blank_session`); every test seeds its own chain, nothing is borrowed.
"""
from __future__ import annotations

import pytest

from app.models.access import ContactFieldReveal
from app.services import contact_field_reveal_service as svc
from tests._cost_viewer_seed import COST_PERM, cost_viewer, link_user
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_contact

COST = "purchase_orders.cost"
SELLABLE = "inventory.sellable"
SUPPLIER = "purchase_orders.supplier"
DO_KEYS = sorted(key for key, _label in svc.FIELD_REVEAL_KEYS if key.startswith("delivery_orders."))


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _contact(db) -> str:
    return seed_contact(db)["pk"]


def _row(db, contact_pk: str, key: str, granted: bool = True) -> None:
    db.add(ContactFieldReveal(respond_contact_id=contact_pk, field_key=key, granted=granted))
    db.flush()


def _cost_rows(db, contact_pk: str) -> list[tuple[str, bool]]:
    db.expire_all()
    return sorted(
        (r.field_key, bool(r.granted))
        for r in db.query(ContactFieldReveal).filter(
            ContactFieldReveal.respond_contact_id == contact_pk, ContactFieldReveal.field_key == COST
        )
    )


# ---------------------------------------------------------------- AC-1: contact_can_view_cost


def test_ac1_active_linked_user_with_the_permission_can_view_cost(db):
    from app.services.cost_access import contact_can_view_cost

    pk = _contact(db)
    cost_viewer(db, pk)
    assert contact_can_view_cost(db, pk) is True


def test_ac1_linked_user_without_the_permission_cannot(db):
    from app.services.cost_access import contact_can_view_cost

    pk = _contact(db)
    link_user(db, pk, slugs=("inventory.stock.view",))
    assert contact_can_view_cost(db, pk) is False


def test_ac1_linked_user_with_no_role_at_all_cannot(db):
    from app.services.cost_access import contact_can_view_cost

    pk = _contact(db)
    link_user(db, pk)
    assert contact_can_view_cost(db, pk) is False


def test_ac1_no_linked_user_cannot(db):
    from app.services.cost_access import contact_can_view_cost

    assert contact_can_view_cost(db, _contact(db)) is False


@pytest.mark.parametrize("status", ["INACTIVE", "BLOCKED"])
def test_ac1_a_not_active_linked_user_cannot_even_with_the_permission(db, status):
    from app.services.cost_access import contact_can_view_cost

    pk = _contact(db)
    link_user(db, pk, slugs=(COST_PERM,), status=status)
    assert contact_can_view_cost(db, pk) is False


def test_ac1_admin_role_bypass_can_view_cost(db):
    from app.services.cost_access import contact_can_view_cost

    pk = _contact(db)
    link_user(db, pk, role_slug="admin")
    assert contact_can_view_cost(db, pk) is True


def test_ac1_superadmin_role_bypass_can_view_cost(db):
    from app.services.cost_access import contact_can_view_cost

    pk = _contact(db)
    link_user(db, pk, role_slug="superadmin")
    assert contact_can_view_cost(db, pk) is True


def test_ac1_no_contact_cannot(db):
    from app.services.cost_access import contact_can_view_cost

    assert contact_can_view_cost(db, None) is False
    assert contact_can_view_cost(db, "00000000-0000-0000-0000-000000000000") is False


def test_ac1_a_lookup_error_fails_closed(db):
    from app.services.cost_access import contact_can_view_cost

    class Broken:
        def __getattr__(self, name):
            raise RuntimeError("lookup exploded")

    pk = _contact(db)
    cost_viewer(db, pk)
    assert contact_can_view_cost(Broken(), pk) is False


# ---------------------------------------------------------------- AC-2: granted_keys / granted_keys_for


def test_ac2_no_row_and_a_cost_viewer_user_holds_the_cost_key(db):
    pk = _contact(db)
    cost_viewer(db, pk)
    assert COST in svc.granted_keys(db, pk)
    assert COST in svc.granted_keys_for(db, [pk])[pk]


def test_ac2_a_stored_granted_row_without_a_linked_user_holds_no_cost_key(db):
    pk = _contact(db)
    _row(db, pk, COST, True)
    assert COST not in svc.granted_keys(db, pk)
    assert COST not in svc.granted_keys_for(db, [pk])[pk]


def test_ac2_a_stored_granted_row_with_a_user_lacking_the_permission_holds_no_cost_key(db):
    pk = _contact(db)
    _row(db, pk, COST, True)
    link_user(db, pk, slugs=("inventory.stock.view",))
    assert COST not in svc.granted_keys(db, pk)


def test_ac2_a_stored_granted_row_with_an_inactive_user_holds_no_cost_key(db):
    pk = _contact(db)
    _row(db, pk, COST, True)
    link_user(db, pk, slugs=(COST_PERM,), status="INACTIVE")
    assert COST not in svc.granted_keys(db, pk)


def test_ac2_a_stored_revoked_row_does_not_hide_the_cost_key_from_a_viewer(db):
    pk = _contact(db)
    _row(db, pk, COST, False)
    cost_viewer(db, pk)
    assert COST in svc.granted_keys(db, pk)


def test_ac2_admin_role_contact_holds_the_cost_key(db):
    pk = _contact(db)
    link_user(db, pk, role_slug="admin")
    assert COST in svc.granted_keys(db, pk)


def test_ac2_granted_keys_for_decides_each_contact_on_its_own(db):
    viewer, plain, stored_only, inactive = _contact(db), _contact(db), _contact(db), _contact(db)
    cost_viewer(db, viewer)
    link_user(db, plain, slugs=("inventory.stock.view",))
    _row(db, stored_only, COST, True)
    link_user(db, inactive, slugs=(COST_PERM,), status="INACTIVE")
    held = svc.granted_keys_for(db, [viewer, plain, stored_only, inactive])
    assert COST in held[viewer]
    assert COST not in held[plain]
    assert COST not in held[stored_only]
    assert COST not in held[inactive]
    # keyed by every id as given, same as before
    assert set(held) == {viewer, plain, stored_only, inactive}


def test_ac2_granted_keys_and_granted_keys_for_agree(db):
    a, b = _contact(db), _contact(db)
    cost_viewer(db, a)
    _row(db, b, COST, True)
    both = svc.granted_keys_for(db, [a, b])
    assert both[a] == svc.granted_keys(db, a)
    assert both[b] == svc.granted_keys(db, b)


def test_ac2_other_keys_still_follow_their_stored_row(db):
    pk = _contact(db)
    _row(db, pk, SELLABLE, True)
    _row(db, pk, SUPPLIER, False)
    keys = svc.granted_keys(db, pk)
    assert SELLABLE in keys
    assert SUPPLIER not in keys


def test_ac2_a_cost_viewer_user_does_not_leak_other_non_default_keys(db):
    pk = _contact(db)
    cost_viewer(db, pk)
    assert svc.granted_keys(db, pk) == sorted([*DO_KEYS, COST])


def test_ac2_do_keys_stay_default_on_and_a_revoked_one_stays_hidden(db):
    pk = _contact(db)
    _row(db, pk, "delivery_orders.warehouse", False)
    assert svc.granted_keys(db, pk) == [k for k in DO_KEYS if k != "delivery_orders.warehouse"]


# ---------------------------------------------------------------- AC-6: the checklist and the save


def test_ac6_the_checklist_no_longer_offers_the_cost_key(db):
    keys = [item["key"] for item in svc.field_reveal_keys()]
    assert COST not in keys
    assert SELLABLE in keys and SUPPLIER in keys  # the rest of the checklist is intact


def test_ac6_a_save_naming_the_cost_key_creates_no_row(db):
    pk = _contact(db)
    result = svc.set_granted_keys(db, pk, [SELLABLE, COST], actor_id=None)
    assert _cost_rows(db, pk) == []
    assert COST not in result
    assert SELLABLE in result


def test_ac6_a_save_never_grants_cost_to_a_user_less_contact(db):
    pk = _contact(db)
    svc.set_granted_keys(db, pk, [COST], actor_id=None)
    assert COST not in svc.granted_keys(db, pk)
    assert _cost_rows(db, pk) == []


def test_ac6_an_existing_granted_row_is_left_untouched_by_a_save_that_omits_it(db):
    pk = _contact(db)
    _row(db, pk, COST, True)
    svc.set_granted_keys(db, pk, [SELLABLE], actor_id=None)
    assert _cost_rows(db, pk) == [(COST, True)]


def test_ac6_an_existing_revoked_row_is_left_untouched_by_a_save_that_names_it(db):
    pk = _contact(db)
    _row(db, pk, COST, False)
    svc.set_granted_keys(db, pk, [SELLABLE, COST], actor_id=None)
    assert _cost_rows(db, pk) == [(COST, False)]


def test_ac6_a_save_does_not_change_what_a_cost_viewer_holds(db):
    pk = _contact(db)
    cost_viewer(db, pk)
    result = svc.set_granted_keys(db, pk, [], actor_id=None)
    assert COST in result
    assert _cost_rows(db, pk) == []


def test_ac6_non_cost_keys_still_save_and_revoke_as_before(db):
    pk = _contact(db)
    assert svc.set_granted_keys(db, pk, [*DO_KEYS, SELLABLE, SUPPLIER], actor_id=None) == sorted(
        [*DO_KEYS, SELLABLE, SUPPLIER]
    )
    assert svc.set_granted_keys(db, pk, [*DO_KEYS, SUPPLIER], actor_id=None) == sorted([*DO_KEYS, SUPPLIER])


# ---------------------------------------------------------------- AC-9: unchanged


def test_ac9_staff_reveal_keys_still_answer_the_cost_key_to_the_permission(db):
    from app.models.access import RespondContact  # noqa: F401 - registers the model set

    holder = link_user(db, _contact(db), slugs=(COST_PERM,))
    other = link_user(db, _contact(db), slugs=("inventory.stock.view",))
    assert COST in svc.staff_reveal_keys(db, holder)
    assert COST not in svc.staff_reveal_keys(db, other)


def test_ac9_staff_reveal_keys_ignore_any_stored_cost_row(db):
    pk = _contact(db)
    _row(db, pk, COST, True)
    user_id = link_user(db, pk, slugs=("inventory.stock.view",))
    assert COST not in svc.staff_reveal_keys(db, user_id)


def test_ac9_staff_cost_screens_still_follow_holds_cost_view(db):
    from app.services.cost_access import holds_cost_view

    has = link_user(db, _contact(db), slugs=(COST_PERM,))
    lacks = link_user(db, _contact(db), slugs=("inventory.stock.view",))
    assert holds_cost_view(db, {"id": has}) is True
    assert holds_cost_view(db, {"id": lacks}) is False


def test_ac9_the_cost_permission_gate_for_staff_screens_is_unchanged(db):
    from app.services.cost_access import COST_VIEW_PERM, can_view_cost

    assert COST_VIEW_PERM == COST_PERM
    assert can_view_cost(db, link_user(db, _contact(db), slugs=(COST_PERM,))) is True
    assert can_view_cost(db, link_user(db, _contact(db), slugs=())) is False
