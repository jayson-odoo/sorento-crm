"""COMBO-SEED-FLYER follow-up 2, review round: guards plus AC-D3b / AC-D2b (red tests, written first).

Same realistic case as test_remove_flyer_seed_duplicates.py (owner combo + importer-made duplicate),
varying one thing each.
"""
from __future__ import annotations

import re
import uuid

from app.models.access import RespondContact
from app.models.audit import AuditLog
from app.models.base import company_scope
from app.models.price_tag import PriceTagRequest, PriceTagRequestLine
from app.models.product import Product
from app.models.product_combo import ProductCombo, ProductComboPart
from app.models.resources import Attachment
from app.services.product_combo_service import ProductComboService

from tests._mc_lookup_seed import attachment, attachment_type
from tests._pg_fixture import unique_code
from tests import test_remove_flyer_seed_duplicates as base
from tests.test_remove_flyer_seed_duplicates import (
    OWNER_USER,
    _cleanup,
    _cleanup_script,
    _combos,
    _counts,
    _entry,
    _import,
    _line,
    _prod,
    _setup,
)

# The audit log is append-only (a DELETE is refused), and an ORM edit of the combo writes its own audit
# row. So a case that needs "no audit row" or "an unaudited edit" is built with Core statements, which
# the audit listeners never see.
db = base.db


def _creation_audit(db, dup_id):
    with company_scope(db, None):
        rows = db.query(AuditLog).filter(AuditLog.entity_id == dup_id).all()
    return [r for r in rows if r.job_id == "import_product_combos" and r.action in ("CREATE", "INSERT")]


def _add_audit(db, entity_type, entity_id, root_id=None):
    with company_scope(db, None):
        db.add(AuditLog(id=str(uuid.uuid4()), entity_type=entity_type, entity_id=entity_id, action="UPDATE",
                        root_entity_id=root_id, user_id=OWNER_USER, actor_type="user", job_id=None,
                        old_values={"a": 1}, new_values={"a": 2}))
        db.commit()


def _core_combo(db, host_code, name, created_by=None):
    """A combo inserted without the ORM, so no audit row is written for it."""
    combo_id = str(uuid.uuid4())
    with company_scope(db, None):
        host = db.query(Product).filter(Product.product_code == host_code).one()
        db.execute(ProductCombo.__table__.insert().values(
            id=combo_id, host_product_id=host.id, name=name, created_by=created_by))
        db.commit()
    return combo_id


def _setup_unaudited_owner(db, tmp_path):
    """Owner combo with created_by NULL and no audit row; then the importer's duplicate."""
    _prod(db, "ZZRH1")
    _prod(db, "ZZRP1")
    owner_id = _core_combo(db, "ZZRH1", "OWNER PACK")
    _import(db, tmp_path, [_entry("ZZRH1", "H + P", "ZZRP1")])
    dup = _combos(db, "ZZRH1", "H + P")
    assert len(dup) == 1
    return owner_id, dup[0]


# --------------------------------------------------------------------------- guards


def test_guard_price_tag_request_line_keeps_the_duplicate(db, tmp_path):
    _cleanup_script()
    _, dup = _setup(db, tmp_path)
    with company_scope(db, None):
        contact = RespondContact(id=str(uuid.uuid4()), phone_number=f"+60{uuid.uuid4().hex[:9]}",
                                 name=unique_code("contact"))
        db.add(contact)
        db.flush()
        request = PriceTagRequest(id=str(uuid.uuid4()), contact_id=contact.id, doc_number=unique_code("PTR")[:30],
                                  company_id=dup.host.company_id if hasattr(dup, "host") else
                                  db.query(Product).filter(Product.id == dup.host_product_id).one().company_id)
        db.add(request)
        db.flush()
        db.add(PriceTagRequestLine(id=str(uuid.uuid4()), request_id=request.id, line_type="product",
                                   product_id=dup.host_product_id, combo_id=dup.id))
        db.commit()
    code, out = _cleanup(db, tmp_path, apply=True)
    verdict, _h, _n, _o, details = _line(out, "H + P")
    assert verdict == "KEEP" and "price tag request" in details.lower()
    assert len(_combos(db, "ZZRH1", "H + P")) == 1


def test_guard_no_importer_creation_row_is_kept(db, tmp_path):
    _cleanup_script()
    _prod(db, "ZZRH1")
    _prod(db, "ZZRP1")
    base._owner_combo(db, "ZZRH1")
    dup_id = _core_combo(db, "ZZRH1", "H + P")
    assert _creation_audit(db, dup_id) == []
    code, out = _cleanup(db, tmp_path, apply=True)
    assert _line(out, "H + P")[0] == "KEEP"
    assert len(_combos(db, "ZZRH1", "H + P")) == 1


def test_guard_user_audit_on_a_part_keeps_the_duplicate(db, tmp_path):
    _cleanup_script()
    _, dup = _setup(db, tmp_path)
    with company_scope(db, None):
        part = db.query(ProductComboPart).filter(ProductComboPart.combo_id == dup.id).first()
        assert part is not None
        part_id = part.id
    _add_audit(db, "product_combo_part", part_id, root_id=dup.id)
    code, out = _cleanup(db, tmp_path, apply=True)
    verdict, _h, _n, _o, details = _line(out, "H + P")
    assert verdict == "KEEP" and "touched" in details.lower()
    assert len(_combos(db, "ZZRH1", "H + P")) == 1


def test_guard_dry_run_is_read_only_first_and_never_calls_delete(db, tmp_path, monkeypatch):
    _cleanup_script()
    _setup(db, tmp_path)
    calls = []
    real_execute = db.execute

    def spy(statement, *args, **kwargs):
        calls.append(str(statement))
        return real_execute(statement, *args, **kwargs)

    deleted = []
    monkeypatch.setattr(db, "execute", spy)
    monkeypatch.setattr(ProductComboService, "delete", lambda self, combo_id: deleted.append(combo_id))
    code, out = _cleanup(db, tmp_path)
    assert code == 0, out
    assert calls and "SET TRANSACTION READ ONLY" in calls[0].upper()
    assert deleted == []


# --------------------------------------------------------------------------- AC-D3b / AC-D2b


def test_ac_d3b_owner_combo_not_person_made_keeps_the_duplicate(db, tmp_path):
    _cleanup_script()
    owner_id, dup = _setup_unaudited_owner(db, tmp_path)
    before = _counts(db)
    code, out = _cleanup(db, tmp_path, apply=True)
    verdict, _h, _n, _o, details = _line(out, "H + P")
    assert verdict == "KEEP"
    assert "OWNER PACK" in details
    assert len(_combos(db, "ZZRH1", "H + P")) == 1
    assert _counts(db) == before


def test_ac_d3b_owner_combo_edited_by_a_user_allows_delete(db, tmp_path):
    _cleanup_script()
    owner_id, dup = _setup_unaudited_owner(db, tmp_path)
    with company_scope(db, None):
        etype = db.query(AuditLog).filter(AuditLog.entity_id == dup.id).first().entity_type
    _add_audit(db, etype, owner_id)
    code, out = _cleanup(db, tmp_path, apply=True)
    assert _line(out, "H + P")[0] == "DELETE"
    assert _combos(db, "ZZRH1", "H + P") == []


def test_ac_d3b_duplicate_with_a_picture_is_kept(db, tmp_path):
    _cleanup_script()
    _, dup = _setup(db, tmp_path)
    with company_scope(db, None):
        kind = attachment_type(db)
        picture = attachment(db, type_id=kind.id)
        db.execute(ProductCombo.__table__.update().where(ProductCombo.id == dup.id)
                   .values(image_attachment_id=picture.id))
        db.commit()
        assert db.query(Attachment).filter(Attachment.id == picture.id).count() == 1
    code, out = _cleanup(db, tmp_path, apply=True)
    verdict, _h, _n, _o, details = _line(out, "H + P")
    assert verdict == "KEEP" and "picture" in details.lower()
    assert len(_combos(db, "ZZRH1", "H + P")) == 1


def test_ac_d2b_delete_line_names_the_creation_time(db, tmp_path):
    _cleanup_script()
    _, dup = _setup(db, tmp_path)
    stamps = [r.changed_at for r in _creation_audit(db, dup.id)] + [dup.created_at]
    allowed = {s.strftime("%d/%m/%Y") for s in stamps if s is not None}
    code, out = _cleanup(db, tmp_path)
    verdict, _h, _n, _o, details = _line(out, "H + P")
    assert verdict == "DELETE"
    found = re.search(r"(\d{2}/\d{2}/\d{4}) \d{2}:\d{2}", details)
    assert found, details
    assert found.group(1) in allowed, (details, allowed)
