"""PRICETAG-COMBO-FORMAT S2: a combo description is sanitised on every write path.

UAC: documentation/plans/dealer-kit/pricetag-combo-format-acceptance-criteria.md, AC-9 to AC-11.

Written test-FIRST (PRINCIPLES.md Phase 2). `sanitise_tag_html` is not wired into
`product_combo_service` yet, so a stored `<img onerror>` and an empty-markup string are the
red lines; the 5000-character limit must move from the raw schema field to the SANITISED value.

Harness (host product, caller, permission patch) is reused from `tests/test_product_combos.py`.

KILL: bypass the sanitiser in `product_combo_service.update` -> tests 1, 2 and the 6000-char
case go red.
"""
from __future__ import annotations

import pytest

from tests._tag_rich_fixture import E1_HTML
from tests.test_product_combos import (  # noqa: F401  (db and _clear_overrides are fixtures)
    COMBO,
    COMBOS,
    EDIT,
    VIEW,
    _caller,
    _clear_overrides,
    _combo,
    _product,
    db,
)


def _patch(client, combo_id, **body):
    return client.patch(COMBO.format(combo_id=combo_id), json=body)


def _setup(db, monkeypatch):
    host = _product(db, "SRTBF11416")
    combo = _combo(db, host, "3 in 1")
    return host, combo, _caller(db, {VIEW, EDIT}, monkeypatch)


# --------------------------------------------------------------------------- AC-9
def test_patch_stores_e1_and_get_returns_it(db, monkeypatch):
    """AC-9: E1 is stored byte-equal after sanitising and read back."""
    host, combo, client = _setup(db, monkeypatch)
    res = _patch(client, combo.id, description=E1_HTML)
    assert res.status_code == 200, res.text
    assert res.json()["description"] == E1_HTML
    listed = client.get(COMBOS.format(product_id=host.id)).json()["data"]
    assert [row["description"] for row in listed if row["id"] == combo.id] == [E1_HTML]


def test_patch_strips_an_img_with_an_event_handler(db, monkeypatch):
    """AC-9: the stored value has no `img`. KILL: bypass the sanitiser in update."""
    _host, combo, client = _setup(db, monkeypatch)
    res = _patch(client, combo.id, description="<p>a<img src=x onerror=alert(1)></p>")
    assert res.status_code == 200, res.text
    assert res.json()["description"] == "<p>a</p>"
    db.expire_all()
    from app.models.product_combo import ProductCombo

    assert db.get(ProductCombo, combo.id).description == "<p>a</p>"


def test_create_sanitises_a_description_sent_with_the_name(db, monkeypatch):
    """AC-9: combo create. The create body carries `description` (contract: `product_combo_service`
    create + update); today the field is ignored, so it stores nothing and this is red."""
    host = _product(db, "SRTBF11829")
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    res = client.post(
        COMBOS.format(product_id=host.id),
        json={"name": "2 in 1", "description": "<p>a<img src=x onerror=alert(1)><script>x</script></p>"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["description"] == "<p>a</p>"


# --------------------------------------------------------------------------- AC-10
@pytest.mark.parametrize("empty", ["<p></p>", "  ", "<p> </p>", "<p><strong></strong></p>"])
def test_empty_markup_stores_null(db, monkeypatch, empty):
    _host, combo, client = _setup(db, monkeypatch)
    assert _patch(client, combo.id, description="<p>first</p>").status_code == 200
    res = _patch(client, combo.id, description=empty)
    assert res.status_code == 200, res.text
    assert res.json()["description"] is None


def test_the_limit_applies_to_the_sanitised_value(db, monkeypatch):
    """AC-10: 5000 is fine, 5001 after sanitising is a 422, and a 6000-character value that
    sanitises to far fewer is accepted (the schema's raw max_length must go)."""
    _host, combo, client = _setup(db, monkeypatch)

    at_limit = "<p>" + "a" * 4993 + "</p>"
    assert len(at_limit) == 5000
    assert _patch(client, combo.id, description=at_limit).status_code == 200

    over = "<p>" + "a" * 4994 + "</p>"
    assert len(over) == 5001
    assert _patch(client, combo.id, description=over).status_code == 422

    noisy = "<p>" + '<span class="aaaaaaaaaa" id="b">x</span>' * 150 + "</p>"
    assert len(noisy) > 6000
    res = _patch(client, combo.id, description=noisy)
    assert res.status_code == 200, res.text
    assert res.json()["description"] == "<p>" + "<span>x</span>" * 150 + "</p>"


# --------------------------------------------------------------------------- AC-11
def test_legacy_plain_text_is_stored_unchanged(db, monkeypatch):
    _host, combo, client = _setup(db, monkeypatch)
    legacy = "SRTBF11416 (CABINET)\nL400xW345xH390mm"
    res = _patch(client, combo.id, description=legacy)
    assert res.status_code == 200, res.text
    assert res.json()["description"] == legacy


# --------------------------------------------------------------------------- captain ruling 5 Nov
def test_a_bare_img_with_no_leading_block_stores_null(db, monkeypatch):
    """Plain-text mode: a value that is only a tag has no text left, so it clears the field."""
    _host, combo, client = _setup(db, monkeypatch)
    assert _patch(client, combo.id, description="<p>first</p>").status_code == 200
    res = _patch(client, combo.id, description="<img src=x onerror=alert(1)>")
    assert res.status_code == 200, res.text
    assert res.json()["description"] is None
    db.expire_all()
    from app.models.product_combo import ProductCombo

    assert db.get(ProductCombo, combo.id).description is None


def test_a_bare_img_before_text_keeps_only_the_text(db, monkeypatch):
    _host, combo, client = _setup(db, monkeypatch)
    res = _patch(client, combo.id, description="<img src=x onerror=alert(1)>x")
    assert res.status_code == 200, res.text
    assert res.json()["description"] == "x"


def test_a_stray_less_than_in_plain_text_is_stored_unchanged(db, monkeypatch):
    _host, combo, client = _setup(db, monkeypatch)
    res = _patch(client, combo.id, description="L400 < 500mm")
    assert res.status_code == 200, res.text
    assert res.json()["description"] == "L400 < 500mm"


# --------------------------------------------------------------------------- fix round 1 (R3, R4)
def test_r3_a_raw_value_over_the_schema_limit_is_422_before_sanitising(db, monkeypatch):
    """R3: `max_length=20000` on the raw field (the 5000 after sanitising stays)."""
    host, combo, client = _setup(db, monkeypatch)
    assert _patch(client, combo.id, description="a" * 100_000).status_code == 422
    assert _patch(client, combo.id, description="a" * 20_001).status_code == 422
    created = client.post(
        COMBOS.format(product_id=host.id), json={"name": "big", "description": "a" * 100_000}
    )
    assert created.status_code == 422, created.text


def test_r3_the_raw_limit_is_20000_not_less(db, monkeypatch):
    """A 20000-character raw value that sanitises under 5000 still saves."""
    _host, combo, client = _setup(db, monkeypatch)
    # One long dropped attribute: ~19.9k raw, sanitises to "<p><span>x</span></p>".
    noisy = '<p><span class="' + "c" * 19900 + '">x</span></p>'
    assert 19000 < len(noisy) <= 20000
    res = _patch(client, combo.id, description=noisy)
    assert res.status_code == 200, res.text


def test_r4_a_nul_byte_is_stripped_not_a_500(db, monkeypatch):
    """R4: Postgres refuses NUL in text; the sanitiser removes it first."""
    _host, combo, client = _setup(db, monkeypatch)
    res = _patch(client, combo.id, description="<p>a\u0000b</p>")
    assert res.status_code == 200, res.text
    assert res.json()["description"] == "<p>ab</p>"
    res = _patch(client, combo.id, description="a\u0001b\nc")
    assert res.status_code == 200, res.text
    assert res.json()["description"] == "ab\nc"
