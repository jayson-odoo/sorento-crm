from tests.test_report_unify_screen import *
from tests.test_report_unify_screen import _world, _ask_total

def test_probe(client, db):
    w = _world(db)
    for b in ("delivered","ordered","outstanding","pending_delivery","invoiced"):
        print("PROBE", b, _ask_total(client, db, b, spec=["trap_type:p_trap"]), _ask_total(client, db, b))
    print("PROBE unpaid", _ask_total(client, db, "unpaid"), _ask_total(client, db, "unpaid", customer_ids=[w.c1.id]))
