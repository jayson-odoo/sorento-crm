"""Seed the CONFIRM-PREVIEW-STALE browser-verification scenario on an ISOLATED local database.

Owner's case (2 Nov 2026): a project sales order whose lines are all delivered in full, one line
confirmed BEFORE delivery, then AutoCount moves that line's date 28/09/2026 -> 02/11/2026 as a
pending planning-change batch, and a saved board draft on that line differs from the change's
suggestion.

Never run against a shared database. Run from sorento_crm_backend/:

    SORENTO_ENV_FILE=.env.ci-tests E2E_EMAIL=... E2E_PASSWORD=... \
        venv/bin/python -m scripts.seed_confirm_preview_stale

Needs the blank bootstrapped schema (scripts/cloud-env-setup.sh). All data is ZZT-prefixed fake
data. It writes through the same services/routes the tests use, on a normal committed session.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal

import bcrypt

os.environ.setdefault("SORENTO_ENV_FILE", ".env.ci-tests")

from app.database import SessionLocal  # noqa: E402
from app.models.base import company_scope  # noqa: E402
from app.models.company import UserCompany  # noqa: E402
from app.models.user import User, UserRole, UserRoleAssignment  # noqa: E402
from app.services import project_seed_service  # noqa: E402
from app.services.project_service import register_project  # noqa: E402
from app.services.scm.outstanding_diff import DATE_MOVED  # noqa: E402
from tests.scm.test_line_splits_api import _mirror  # noqa: E402
from app.services.scm.outstanding_diff import Change, Line  # noqa: E402
from tests.test_planning_change_apply_on_board import _build, _confirm  # noqa: E402
from tests.test_planning_changes import (  # noqa: E402
    BASE,
    _client,
    _core_so,
    _line_payload,
    _product,
    _project_so,
    _restore,
    _sorento,
    _uid,
    _warehouse,
)

WAS = date(2026, 9, 28)


def _date_change(core_line, *, so_number, item_code, location, old_date, new_date, qty):
    """The AutoCount date move, keyed by the REAL item code and location of the line (the
    tests' own `_change` hardcodes a fake code, which the board then shows as a second row)."""
    before = Line(doc_number=so_number, item_code=item_code, location=location, qty=float(qty),
                  required_date=old_date, row_ref=str(core_line.id))
    after = Line(doc_number=so_number, item_code=item_code, location=location, qty=float(qty),
                 required_date=new_date, row_ref="1")
    return Change(DATE_MOVED, so_number, item_code, location, before=before, after=after)
NOW = date(2026, 11, 2)


def main() -> None:
    email = os.environ["E2E_EMAIL"].strip().lower()
    password = os.environ["E2E_PASSWORD"]
    db = SessionLocal()
    company_id = _sorento(db)
    assert company_id, "SRT company missing: run scripts/cloud-env-setup.sh first"

    # Superadmin login user (bcrypt hash, the way /auth/login checks it).
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            id=_uid(), email=email, name="ZZT Planner", status="ACTIVE",
            password=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        )
        db.add(user)
        db.flush()
        role = db.query(UserRole).filter(UserRole.slug == "superadmin").one()
        db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
        db.add(UserCompany(company_id=company_id, user_id=user.id))
        user.last_active_company_id = company_id
        db.commit()
    actor = str(user.id)

    project_seed_service.run(db, company_id=company_id)
    project = register_project(
        db, company_id=company_id, actor_user_id=actor, developer_party_id=None,
        title=f"ZZT Stale Preview Tower {_uid()[:6]}",
    )
    product = _product(db)
    pool_wh = _warehouse(db, f"ZZT-BRW-{_uid()[:4]}", segment="dealer")
    own_wh = _warehouse(db, f"ZZT-IB-{_uid()[:4]}", segment="project",
                        pool_warehouse_id=pool_wh.id)
    db.commit()

    client, originals = _client(db, actor)
    try:
        with company_scope(db, frozenset({company_id})):
            core_so = _core_so(db, company_id)
            order = _project_so(db, project, so_id=core_so.id,
                                autocount_doc_no=core_so.so_number)
            db.commit()
            c10, l10 = _mirror(db, order, core_so, product, own_wh,
                               line_no=10, qty=3, when=WAS)
            others = []
            for line_no, qty in ((20, 5), (30, 8), (40, 2)):
                c, ln = _mirror(db, order, core_so, product, own_wh,
                                line_no=line_no, qty=qty, when=WAS)
                others.append(c)
            db.commit()

            # Line 10 is confirmed BEFORE delivery. Buy 3: a Borrow needs donor stock and a
            # reason on this engine, and the review words are the same for the stale check.
            resp = _confirm(client, order.id, [_line_payload(l10.id, buy_qty="3")])
            assert resp.status_code == 200, resp.text

            # Everything delivered in full.
            c10.qty_delivered = Decimal("3")
            for c in others:
                c.qty_delivered = c.qty_ordered
            db.commit()

            # AutoCount moves line 10: 28/09 -> 02/11 (the book re-upload wrote the new date).
            c10.required_date = NOW
            l10.delivery_date = NOW
            db.commit()
            batch = _build(
                type("W", (), {"db": db, "actor": actor})(),
                [_date_change(c10, so_number=core_so.so_number, item_code=product.product_code,
                              location=own_wh.warehouse_code, old_date=WAS, new_date=NOW,
                              qty=3)],
                core_so, [str(c10.id)],
            )
            assert batch is not None, "pending change batch was not built"

            # Saved board draft on that line that differs from the suggestion.
            board = client.get(
                f"{BASE}/fulfilment-planning/board", params={"orders": core_so.so_number}
            )
            assert board.status_code == 200, board.text
            mine = [c for c in board.json()["contributions"]
                    if c["line_id"] == str(c10.id) and not c.get("cancelled")]
            assert mine, "line 10 not on the board"
            key = mine[0]["key"]
            print("contribution key:", key)
            print("SO number:", core_so.so_number)
            print("project:", project.title)
    finally:
        _restore(originals)
        db.close()

    # The service the PUT route calls, in a FRESH process: once app.main is imported (the tests'
    # TestClient helpers do that) the company scope no longer resolves this line for a bare
    # session, so the save runs where only the models and the service are imported.
    import subprocess

    code = """
import sys
from app.database import SessionLocal
from app.models.base import company_scope
from app.services import project_line_draft_service as d
company_id, actor, key = sys.argv[1:4]
db = SessionLocal()
with company_scope(db, frozenset({company_id})):
    saved = d.save_draft(db, key, decision={"verdict": "amended", "buy_qty": "2", "reserve": [],
        "borrow": [], "reason": "ZZT keep my own split"}, actor_user_id=actor)
    db.commit()
print("draft saved:", saved["decision"], saved["saved_at"])
"""
    subprocess.run([sys.executable, "-c", code, str(company_id), actor, key], check=True)


if __name__ == "__main__":
    sys.exit(main())
