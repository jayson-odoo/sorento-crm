from .test_oi_waiting_for_cs import env, _world, _push, OLD_DATE
from sqlalchemy import text
def test_dbg(env):
    w = _world(env, "date")
    before = env.so_lines(w.header["id"])
    _push(w, dict(w.record, lines=[dict(w.x, required_date=OLD_DATE, product_ref=env.product2_ref), w.y]))
    after = env.so_lines(w.header["id"])
    print("DBG", [(l["id"][:6], l.get("product_id"), l.get("required_date")) for l in before], [(l["id"][:6], l.get("product_id"), l.get("required_date")) for l in after])
    assert 0
