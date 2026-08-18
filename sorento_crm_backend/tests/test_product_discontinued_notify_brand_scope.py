"""Per-(company, brand) recipient scoping for the product-discontinued notice.

Covers documentation/plans/product-discontinued-brand-scope-acceptance-criteria.md
AC-1, AC-3 through AC-9 (AC-2 is the migration backfill, covered in
tests/test_migration_375_user_discontinued_scopes.py; AC-11's FK-cascade half is
covered here too since it is cheap alongside the rest of the scope-row wiring).

``subset_for_scopes`` is pure and importable, so it is the cheapest place to pin
the matching rule itself (AC-5, AC-6); ``run_product_discontinued_check`` is
exercised end to end for the wording/count/link the recipient actually receives
(AC-1, AC-3, AC-4, AC-7, AC-8, AC-9).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.notification import Notification
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.user import User, UserProductDiscontinuedScope
from app.services.company_scope import DEFAULT_COMPANY_ID
import app.services.product_discontinued_notify_service as svc
from tests._pg_fixture import blank_session, unique_code

SORENTO = DEFAULT_COMPANY_ID
MOCHA = "00000000-0000-0000-0000-000000000002"


@pytest.fixture
def db():
    with blank_session() as session:
        # All-companies scope: the run must be able to see Mocha rows too, exactly
        # as the scheduler runs it (mirrors test_product_discontinued_notify_company_scope.py).
        set_company_scope(session, None)
        yield session


def _second_company(db, company_id: str = MOCHA, name: str = "Mocha") -> str:
    db.add(Company(id=company_id, name=name, code=unique_code(name[:3])[:20]))
    db.flush()
    return company_id


def _refs(db):
    if not hasattr(db, "_refs"):
        cat, uom = str(uuid.uuid4()), str(uuid.uuid4())
        db.add(ProductCategory(id=cat, category_code=unique_code("CAT"), category_name="ZZT Category"))
        db.add(UnitOfMeasure(id=uom, uom_code=unique_code("EA")[:16], uom_name="ZZT Each"))
        db.flush()
        db._refs = (cat, uom)
    return db._refs


def _brand(db, *, company_id: str, name: str = "Brand") -> str:
    b = Brand(
        id=str(uuid.uuid4()),
        brand_code=unique_code(name[:4]),
        brand_name=f"ZZT {name}",
        is_active=True,
        company_id=company_id,
    )
    db.add(b)
    db.flush()
    return str(b.id)


def _product(db, *, code: str, company_id: str, brand_id: str | None = None) -> Product:
    cat, uom = _refs(db)
    p = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        category_id=cat,
        base_uom_id=uom,
        list_price=10,
        is_active=True,
        is_discontinued=True,
        company_id=company_id,
        brand_id=brand_id,
    )
    db.add(p)
    return p


def _user(db, *, email: str, email_pref: bool = True) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=email,
        name=email.split("@")[0],
        status="ACTIVE",
        notify_email_on_product_discontinued=email_pref,
    )
    db.add(u)
    db.flush()
    return u


def _scope(db, user_id: str, *, company_id: str | None = None, brand_id: str | None = None):
    row = UserProductDiscontinuedScope(
        id=str(uuid.uuid4()), user_id=user_id, company_id=company_id, brand_id=brand_id
    )
    db.add(row)
    return row


def _note_for(db, user_id: str) -> Notification:
    return db.query(Notification).filter(Notification.user_id == user_id).one()


def _link_params(link: str) -> dict:
    from urllib.parse import parse_qs, urlsplit

    return {k: v[0] for k, v in parse_qs(urlsplit(link).query).items()}


# --------------------------------------------------------------------------- #
# subset_for_scopes - the pure matching rule (AC-5, AC-6)
# --------------------------------------------------------------------------- #


def test_subset_all_all_scope_takes_the_whole_batch_no_brand_filter():
    pending = ["p1", "p2"]
    subset, brand_ids = svc.subset_for_scopes([(None, None)], SORENTO, pending)
    assert subset == pending
    assert brand_ids == []


def test_subset_all_brands_for_the_company_takes_the_whole_batch():
    pending = ["p1", "p2"]
    subset, brand_ids = svc.subset_for_scopes([(SORENTO, None)], SORENTO, pending)
    assert subset == pending
    assert brand_ids == []


def test_subset_company_mismatch_on_every_scope_is_empty():
    """AC-5: scopes name a company, but none of them is this batch's company."""
    pending = [type("P", (), {"brand_id": "b1"})()]
    subset, brand_ids = svc.subset_for_scopes([(MOCHA, "b1")], SORENTO, pending)
    assert subset == []
    assert brand_ids == []


def test_subset_specific_brand_filters_to_matching_products_only():
    a = type("P", (), {"brand_id": "brand-a"})()
    b = type("P", (), {"brand_id": "brand-b"})()
    subset, brand_ids = svc.subset_for_scopes([(SORENTO, "brand-a")], SORENTO, [a, b])
    assert subset == [a]
    assert brand_ids == ["brand-a"]


def test_subset_null_brand_product_only_matches_all_brands_scope():
    """AC-6: a product with no brand never matches a specific-brand scope."""
    unbranded = type("P", (), {"brand_id": None})()
    subset, _ = svc.subset_for_scopes([(SORENTO, "brand-a")], SORENTO, [unbranded])
    assert subset == []

    subset_all, _ = svc.subset_for_scopes([(SORENTO, None)], SORENTO, [unbranded])
    assert subset_all == [unbranded]


def test_subset_multiple_specific_brand_scopes_union_and_sort_the_link_ids():
    a = type("P", (), {"brand_id": "zz-brand"})()
    b = type("P", (), {"brand_id": "aa-brand"})()
    c = type("P", (), {"brand_id": "unmatched"})()
    subset, brand_ids = svc.subset_for_scopes(
        [(SORENTO, "zz-brand"), (SORENTO, "aa-brand")], SORENTO, [a, b, c]
    )
    assert set(subset) == {a, b}
    assert brand_ids == ["aa-brand", "zz-brand"]  # sorted


# --------------------------------------------------------------------------- #
# AC-1: an all/all scope is byte-identical to pre-feature behaviour
# --------------------------------------------------------------------------- #


def test_ac1_all_all_scope_receives_the_full_batch_with_the_plain_link(db):
    _product(db, code="ZZT-A", company_id=SORENTO)
    _product(db, code="ZZT-B", company_id=SORENTO)
    user = _user(db, email=f"{unique_code('kia')}@zzt.test")
    _scope(db, user.id)  # (NULL, NULL)
    db.commit()

    out = svc.run_product_discontinued_check(db)

    assert out["subscribers"] == 1
    note = _note_for(db, user.id)
    assert note.title == "2 products discontinued"
    link = (note.data or {}).get("discontinued_link", "")
    assert f"discontinued_batch_id={out['batch_id']}" in link
    assert "brand_id=" not in link


# --------------------------------------------------------------------------- #
# AC-3: the Kia Yee scenario, end to end
# --------------------------------------------------------------------------- #


def test_ac3_kia_yee_scenario(db):
    mocha_company = _second_company(db)
    sorento_mocha_brand = _brand(db, company_id=SORENTO, name="Mocha")
    sorento_other_brand = _brand(db, company_id=SORENTO, name="Other")

    _product(db, code="ZZT-SM", company_id=SORENTO, brand_id=sorento_mocha_brand)
    _product(db, code="ZZT-SO", company_id=SORENTO, brand_id=sorento_other_brand)
    _product(db, code="ZZT-MC1", company_id=mocha_company)
    _product(db, code="ZZT-MC2", company_id=mocha_company)

    kia_yee = _user(db, email=f"{unique_code('kiayee')}@zzt.test")
    _scope(db, kia_yee.id, company_id=SORENTO, brand_id=sorento_mocha_brand)
    _scope(db, kia_yee.id, company_id=mocha_company, brand_id=None)
    db.commit()

    out = svc.run_product_discontinued_check(db)

    # Top-level "subscribers" is a max-across-companies figure (one company batch
    # per run), so the per-company breakdown is what proves two separate batches
    # each counted her as a subscriber.
    assert {c["company_id"]: c["subscribers"] for c in out["companies"]} == {
        SORENTO: 1,
        mocha_company: 1,
    }
    notes = db.query(Notification).filter(Notification.user_id == kia_yee.id).all()
    assert len(notes) == 2

    by_company = {}
    for company_run in out["companies"]:
        matching = [
            n
            for n in notes
            if (n.data or {}).get("discontinued_batch_id") == company_run["batch_id"]
        ]
        assert len(matching) == 1
        by_company[company_run["company_id"]] = matching[0]

    sorento_note = by_company[SORENTO]
    assert "1 product" in sorento_note.title  # only the Mocha-brand product
    sorento_link = _link_params((sorento_note.data or {}).get("discontinued_link", ""))
    assert sorento_link.get("discontinued_batch_id") == by_company[SORENTO].data["discontinued_batch_id"]
    assert sorento_link.get("brand_id") == sorento_mocha_brand

    mocha_note = by_company[mocha_company]
    assert "2 product" in mocha_note.title  # the whole Mocha-company batch
    mocha_link = _link_params((mocha_note.data or {}).get("discontinued_link", ""))
    assert "brand_id" not in mocha_link


# --------------------------------------------------------------------------- #
# AC-4, AC-5: zero scopes / non-matching scope -> silence
# --------------------------------------------------------------------------- #


def test_ac4_toggle_on_zero_scopes_receives_nothing(db):
    _product(db, code="ZZT-A", company_id=SORENTO)
    user = _user(db, email=f"{unique_code('noscope')}@zzt.test")
    db.commit()

    out = svc.run_product_discontinued_check(db)

    assert out["subscribers"] == 0
    assert out["notified_users"] == 0
    assert db.query(Notification).filter(Notification.user_id == user.id).count() == 0


def test_ac5_scope_matches_company_but_no_brand_receives_nothing(db):
    brand_a = _brand(db, company_id=SORENTO, name="A")
    brand_b = _brand(db, company_id=SORENTO, name="B")
    _product(db, code="ZZT-A", company_id=SORENTO, brand_id=brand_a)
    user = _user(db, email=f"{unique_code('mismatch')}@zzt.test")
    _scope(db, user.id, company_id=SORENTO, brand_id=brand_b)
    db.commit()

    out = svc.run_product_discontinued_check(db)

    assert out["subscribers"] == 0
    assert db.query(Notification).filter(Notification.user_id == user.id).count() == 0


# --------------------------------------------------------------------------- #
# AC-6: an unbranded product only reaches all-brands recipients
# --------------------------------------------------------------------------- #


def test_ac6_unbranded_product_only_reaches_all_brands_scope(db):
    brand_a = _brand(db, company_id=SORENTO, name="A")
    _product(db, code="ZZT-UNBRANDED", company_id=SORENTO, brand_id=None)

    specific = _user(db, email=f"{unique_code('specific')}@zzt.test")
    _scope(db, specific.id, company_id=SORENTO, brand_id=brand_a)

    allbrands = _user(db, email=f"{unique_code('allbrands')}@zzt.test")
    _scope(db, allbrands.id, company_id=SORENTO, brand_id=None)
    db.commit()

    out = svc.run_product_discontinued_check(db)

    assert out["subscribers"] == 1
    assert db.query(Notification).filter(Notification.user_id == specific.id).count() == 0
    assert db.query(Notification).filter(Notification.user_id == allbrands.id).count() == 1


# --------------------------------------------------------------------------- #
# AC-7: stamp-first still holds with scoped recipients
# --------------------------------------------------------------------------- #


def test_ac7_stamp_first_committed_before_send(db):
    p = _product(db, code="ZZT-STAMP", company_id=SORENTO)
    user = _user(db, email=f"{unique_code('stamp')}@zzt.test")
    _scope(db, user.id)
    db.commit()

    out = svc.run_product_discontinued_check(db)

    db.refresh(p)
    assert p.discontinued_notified_at is not None
    assert p.discontinued_notify_batch_id == out["batch_id"]


# --------------------------------------------------------------------------- #
# AC-8: best-effort fan-out preserved with scoped recipients
# --------------------------------------------------------------------------- #


def test_ac8_one_recipient_failure_does_not_abort_the_rest(db, monkeypatch):
    _product(db, code="ZZT-A", company_id=SORENTO)
    bad = _user(db, email=f"{unique_code('bad')}@zzt.test")
    good = _user(db, email=f"{unique_code('good')}@zzt.test")
    _scope(db, bad.id)
    _scope(db, good.id)
    db.commit()

    real = svc.NotificationService.create_with_channel_preferences

    def flaky(self, *args, **kwargs):
        if kwargs.get("user_id") == bad.id:
            raise RuntimeError("simulated send failure")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(svc.NotificationService, "create_with_channel_preferences", flaky)

    out = svc.run_product_discontinued_check(db)

    assert out["subscribers"] == 2
    assert out["notified_users"] == 1
    recipients = {n.user_id for n in db.query(Notification).all()}
    assert recipients == {good.id}


# --------------------------------------------------------------------------- #
# AC-9: task metadata.company_ids composes with per-recipient scopes
# --------------------------------------------------------------------------- #


def test_ac9_run_scoped_to_one_company_then_filtered_by_recipient_scope(db):
    mocha_company = _second_company(db)
    _product(db, code="ZZT-SRT", company_id=SORENTO)
    _product(db, code="ZZT-MCH", company_id=mocha_company)

    mocha_only = _user(db, email=f"{unique_code('mchonly')}@zzt.test")
    _scope(db, mocha_only.id, company_id=mocha_company, brand_id=None)
    db.commit()

    # The scheduler narrows the session to Sorento before calling the job.
    set_company_scope(db, frozenset({SORENTO}))
    out = svc.run_product_discontinued_check(db)

    assert out["pending"] == 1  # only Sorento's product is even seen
    # The recipient's only scope is Mocha, which this run never touched.
    assert out["subscribers"] == 0
    assert db.query(Notification).filter(Notification.user_id == mocha_only.id).count() == 0

    # Widening the scope brings Mocha into view, and the recipient hears about it.
    set_company_scope(db, None)
    out2 = svc.run_product_discontinued_check(db)
    assert out2["pending"] == 1  # Sorento's product was already stamped, so only Mocha's is new
    assert db.query(Notification).filter(Notification.user_id == mocha_only.id).count() == 1


# --------------------------------------------------------------------------- #
# AC-11 (partial): FK cascade on user / company / brand deletion
# --------------------------------------------------------------------------- #


def test_ac11_scope_row_cascades_on_user_delete(db):
    user = _user(db, email=f"{unique_code('cascade')}@zzt.test")
    scope = _scope(db, user.id)
    db.commit()
    scope_id = scope.id

    db.delete(user)
    db.commit()

    assert db.query(UserProductDiscontinuedScope).filter(
        UserProductDiscontinuedScope.id == scope_id
    ).first() is None


def test_ac11_scope_row_cascades_on_company_delete(db):
    """The third arm of the cascade, and the one most likely to be forgotten.

    A company-scoped row is written for a company the install later drops; without
    ON DELETE CASCADE the delete fails on the FK (an admin cannot remove a company)
    or, worse, leaves a scope row pointing at nothing that the fan-out then matches
    against a reused id.
    """
    company_id = str(uuid.uuid4())
    db.add(Company(id=company_id, name="ZZT Cascade Co", code=unique_code("CSC")[:20]))
    db.flush()
    user = _user(db, email=f"{unique_code('cascadecompany')}@zzt.test")
    scope = _scope(db, user.id, company_id=company_id, brand_id=None)
    db.commit()
    scope_id = scope.id

    db.query(Company).filter(Company.id == company_id).delete()
    db.commit()

    assert db.query(UserProductDiscontinuedScope).filter(
        UserProductDiscontinuedScope.id == scope_id
    ).first() is None


def test_ac11_scope_row_cascades_on_brand_delete(db):
    brand_id = _brand(db, company_id=SORENTO, name="Cascade")
    user = _user(db, email=f"{unique_code('cascadebrand')}@zzt.test")
    scope = _scope(db, user.id, company_id=SORENTO, brand_id=brand_id)
    db.commit()
    scope_id = scope.id

    db.query(Brand).filter(Brand.id == brand_id).delete()
    db.commit()

    assert db.query(UserProductDiscontinuedScope).filter(
        UserProductDiscontinuedScope.id == scope_id
    ).first() is None


# --------------------------------------------------------------------------- #
# The fan-out reads its batch from a snapshot, not from expired ORM rows
# --------------------------------------------------------------------------- #


def test_fanout_does_not_reselect_products_per_recipient(db):
    """Every send commits, which expires the ORM rows the fan-out matches against.

    Reading brands off those instances cost one refresh SELECT per product per
    recipient; the snapshot taken before the stamp commit is what keeps the batch
    query at exactly one, however many recipients there are.
    """
    import re

    from sqlalchemy import event

    brand_a = _brand(db, company_id=SORENTO, name="A")
    brand_b = _brand(db, company_id=SORENTO, name="B")
    _product(db, code="ZZT-PA", company_id=SORENTO, brand_id=brand_a)
    _product(db, code="ZZT-PB", company_id=SORENTO, brand_id=brand_b)

    for i in range(3):
        u = _user(db, email=f"{unique_code(f'scoped{i}')}@zzt.test")
        _scope(db, u.id, company_id=SORENTO, brand_id=brand_a)
    db.commit()

    product_selects = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        text = " ".join(statement.split())
        # The blank-schema fixture qualifies table names, so match the column
        # prefix the ORM always renders instead of a bare "FROM products".
        if text.upper().startswith("SELECT") and re.search(r"(?<![\w])products\.", text):
            product_selects.append(text)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", _record)
    try:
        out = svc.run_product_discontinued_check(db)
    finally:
        event.remove(bind, "before_cursor_execute", _record)

    assert out["subscribers"] == 3
    assert out["notified_users"] == 3
    assert len(product_selects) == 1, product_selects
