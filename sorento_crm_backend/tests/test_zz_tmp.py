from tests.test_pricetag_combo_format_browser_fixes import *  # noqa
from tests.test_pricetag_combo_format_browser_fixes import _world, _body, PORTAL_PREVIEW
def test_portal(env):
    db, c, _ = env
    host, combo, t = _world(db)
    r = c.post(PORTAL_PREVIEW, json=_body(host, combo, t))
    print("RES", r.status_code)
    j = r.json()
    ln = j["lines"][0]
    print("LINE", ln["line_id"], ln["list_price"], ln["sell_price"], ln["show_promo_price"], ln["combo"]["description"], list(j["templates"]), t)
    r2 = c.post(PORTAL_PREVIEW, json=_body(host, combo, t, price_type="list")); print("LIST", r2.json()["lines"][0]["show_promo_price"], r2.json()["lines"][0]["list_price"])
