"""The Spec Registry: one vocabulary, read by both the ranker and the chatbot parser.

Spec search only works if the CRM and the n8n parser agree on what a spec key is and
which values it may take. Holding that list in two places guarantees they drift, and
the drift is silent: the parser emits `wall_mounted`, the ranker looks for `wall_hung`,
and every query quietly scores worse with nothing in the logs.

So the registry is the single source of truth. The parser reads it over HTTP to build
its extraction prompt, and the ranker reads the same rows to weight a match.

Ticket: jayson-odoo/sorento-crm#73. Contract:
documentation/plans/products/spec-search-acceptance-criteria.md AC-T0b-01 .. AC-T0b-05.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.product_spec import ProductSpecRegistry
from app.services.product_spec_registry import (
    PILOT_SPEC_KEYS,
    merged_synonyms,
    seed_spec_registry,
)
from tests._pg_fixture import blank_session

ENDPOINT = "/api/v1/master-data/spec-registry"
_USER = {"id": str(uuid.uuid4()), "email": "specsearch@example.com"}
_GRANTED = {
    "master_data.products.view",
    "master_data.products.edit",
    "master_data.spec_registry.view",
    "master_data.spec_registry.edit",
    "master_data.spec_registry.add",
    "master_data.spec_registry.delete",
}


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture()
def client(db, monkeypatch):
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER
    app.dependency_overrides[apply_company_scope] = lambda: None
    # The routes are gated on master_data.products.view / .edit or the spec_registry
    # equivalents. The blank schema has no role grants, so grant them here rather than
    # seeding an entire RBAC chain: this file is testing the registry, and a separate
    # test covers the permissions themselves.
    #
    # Both lookups have to be stubbed. `require_permission_with_api_key` asks
    # `check_user_has_permission`, but `require_any_permission_with_api_key` - which
    # gates the reads and the PATCH, either grant being enough - reads the slug SET
    # instead and never calls the singular check.
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
    )
    monkeypatch.setattr(
        UserPermissionService, "get_user_permission_slugs", lambda self, uid: set(_GRANTED)
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def denied_client(db, monkeypatch):
    """A caller holding no permissions, to prove the route is actually gated."""
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER
    app.dependency_overrides[apply_company_scope] = lambda: None
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: False
    )
    monkeypatch.setattr(UserPermissionService, "get_user_permission_slugs", lambda self, uid: set())
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _keys(db) -> dict[str, ProductSpecRegistry]:
    return {r.spec_key: r for r in db.query(ProductSpecRegistry).all()}


# AC-T0b-02: the pilot seed registers exactly the keys the tracer needs, no more.
def test_seed_registers_exactly_the_pilot_keys(db):
    seed_spec_registry(db)
    assert set(_keys(db)) == set(PILOT_SPEC_KEYS)


def test_every_seeded_key_is_active_and_typed(db):
    seed_spec_registry(db)
    for key, row in _keys(db).items():
        assert row.is_active is True, key
        assert row.data_type in {"enum", "numeric", "boolean"}, key
        assert row.label, key


def test_measured_numeric_keys_carry_a_unit(db):
    """A count has no unit; a measurement states the one it is in.

    Rendering "2 mm" for a double bowl sink would be worse than wrong: it would embed a
    dimension phrase into a sentence the ranker compares against real dimensions. The
    same trap in reverse is why a measurement may no longer assume millimetres - a bin
    is measured in litres and a pump in horsepower, and calling either "mm" would put
    8 next to a 800mm basin as though they were the same kind of number.
    """
    # Counted, not measured: towel bars, bowls, spray patterns, pieces in a set.
    counts = {"bowl_count", "bar_count", "spray_functions", "piece_count", "way_count"}
    # Every unit the vocabulary is allowed to be in. A new one is a deliberate act:
    # the ranker compares like with like, so a unit nothing normalises is a silent
    # mismatch rather than an error.
    units = {"mm", "L", "oz", "hp"}
    seed_spec_registry(db)
    for key, row in _keys(db).items():
        if row.data_type != "numeric":
            continue
        if key in counts:
            assert row.unit is None, key
        else:
            assert row.unit in units, f"{key} is measured in an undeclared unit: {row.unit}"


def test_enum_keys_carry_allowed_values(db):
    seed_spec_registry(db)
    rows = _keys(db)
    # `class` and `brand` are open vocabularies sourced from product_categories, so
    # they are the deliberate exception: a closed list would go stale the moment a
    # category is added.
    for key in ("material", "mounting", "finish", "control_type", "shape"):
        assert rows[key].allowed_values, key


# AC-T0b-03: diameter only exists for shapes that HAVE one. Ungated, it would be
# proposed for a rectangular sink, where it is meaningless.
def test_diameter_is_gated_on_shape(db):
    seed_spec_registry(db)
    gate = _keys(db)["diameter"].applies_when
    assert gate == {"shape": ["round", "square"]}


def test_rectangular_dimensions_are_not_shape_gated(db):
    # Shape is frequently unknown (no ROUND or SQUARE token in the description), and
    # gating length/width on it would drop every unlabelled rectangular product.
    seed_spec_registry(db)
    rows = _keys(db)
    for key in ("dim_length", "dim_width", "dim_height"):
        assert rows[key].applies_when == {}, key


def test_measured_coverage_is_recorded(db):
    # Recorded at seed time so a later reviewer can see WHY a key is weighted low,
    # rather than rediscovering the measurement.
    seed_spec_registry(db)
    assert _keys(db)["material"].measured_coverage > 0


# AC-T0b-05: re-seeding is safe. It runs on every deploy as the map grows.
def test_seed_is_idempotent(db):
    first = seed_spec_registry(db)
    second = seed_spec_registry(db)
    assert first["created"] == len(PILOT_SPEC_KEYS)
    assert second["created"] == 0
    assert second["updated"] == 0


# AC-T0b-05: weights are tuned against the eval baseline by hand. A re-seed that
# reverted that tuning would silently undo the only calibration the ranker has.
def test_reseed_preserves_a_hand_tuned_rank_weight(db):
    seed_spec_registry(db)
    row = _keys(db)["material"]
    row.rank_weight = 9.5
    db.flush()

    seed_spec_registry(db)

    assert float(_keys(db)["material"].rank_weight) == 9.5


def test_reseed_preserves_a_hand_deactivated_key(db):
    seed_spec_registry(db)
    row = _keys(db)["thickness"]
    row.is_active = False
    db.flush()

    seed_spec_registry(db)

    assert _keys(db)["thickness"].is_active is False


def test_reseed_repairs_a_corrupted_allowed_values(db):
    # Vocabulary is owned by the seed, unlike weights and activation which are owned
    # by whoever tuned them. A wrong allowed_values breaks parser and ranker agreement,
    # so it must be repaired rather than preserved.
    seed_spec_registry(db)
    row = _keys(db)["mounting"]
    row.allowed_values = ["nonsense"]
    db.flush()

    result = seed_spec_registry(db)

    assert "wall_hung" in _keys(db)["mounting"].allowed_values
    assert result["updated"] == 1


# AC-T0b-04: the endpoint the n8n parser reads to build its extraction prompt.
def test_endpoint_returns_the_active_registry(client, db):
    seed_spec_registry(db)

    response = client.get(ENDPOINT)

    assert response.status_code == 200
    body = response.json()
    assert {k["spec_key"] for k in body["keys"]} == set(PILOT_SPEC_KEYS)


def test_endpoint_omits_inactive_keys(client, db):
    # bowl_count ships inactive in T1 precisely so it never reaches the parser prompt.
    # If an inactive key leaked, the parser would extract a spec nothing can match.
    seed_spec_registry(db)
    db.query(ProductSpecRegistry).filter(
        ProductSpecRegistry.spec_key == "thickness"
    ).one().is_active = False
    db.flush()

    keys = {k["spec_key"] for k in client.get(ENDPOINT).json()["keys"]}

    assert "thickness" not in keys
    assert "material" in keys


def test_endpoint_carries_the_vocabulary_the_parser_needs(client, db):
    seed_spec_registry(db)

    material = next(
        k for k in client.get(ENDPOINT).json()["keys"] if k["spec_key"] == "material"
    )

    assert material["data_type"] == "enum"
    assert "stainless_steel" in material["allowed_values"]
    assert "s/steel" in [s.lower() for s in material["synonyms"]["stainless_steel"]]


def test_endpoint_exposes_the_diameter_gate(client, db):
    seed_spec_registry(db)

    diameter = next(
        k for k in client.get(ENDPOINT).json()["keys"] if k["spec_key"] == "diameter"
    )

    assert diameter["applies_when"] == {"shape": ["round", "square"]}


def test_endpoint_is_cacheable(client, db):
    # The parser reads this on every turn and it changes about never, so it carries a
    # validator. Without one, a hot path re-renders the whole vocabulary per message.
    seed_spec_registry(db)

    response = client.get(ENDPOINT)

    assert response.headers.get("etag")
    assert response.json()["updated_at"] is not None


def test_endpoint_returns_304_for_a_matching_etag(client, db):
    seed_spec_registry(db)
    etag = client.get(ENDPOINT).headers["etag"]

    again = client.get(ENDPOINT, headers={"If-None-Match": etag})

    assert again.status_code == 304


def test_endpoint_is_permission_gated(denied_client, db):
    seed_spec_registry(db)
    assert denied_client.get(ENDPOINT).status_code == 403


def test_synonyms_map_customer_language_onto_values(db):
    seed_spec_registry(db)
    synonyms = _keys(db)["material"].synonyms
    assert "s/steel" in [s.lower() for s in synonyms["stainless_steel"]]

    mounting = _keys(db)["mounting"].synonyms
    assert "wall mounted" in [s.lower() for s in mounting["wall_hung"]]


def test_every_derived_enum_value_exists_in_the_registry(db):
    """The registry's vocabulary must cover what derivation actually writes.

    Caught in the browser: `pillar_mounted` and `under_counter` were added to the
    derivation tables and not to the registry, so 603 pillar-mounted taps stored a
    value that the enum dropdown could not offer and no customer phrase could resolve.
    The spec was derived, stored, rendered — and unreachable.
    """
    from app.services.product_spec_derivation import (
        CONTROL_TOKENS,
        MATERIAL_TOKENS,
        MOUNTING_TOKENS,
        PRODUCT_TYPE_TOKENS,
        SHAPE_TOKENS,
        SPOUT_TOKENS,
        TRAP_TOKENS,
    )

    seed_spec_registry(db)
    rows = _keys(db)
    for key, table in (
        ("material", MATERIAL_TOKENS),
        ("mounting", MOUNTING_TOKENS),
        ("control_type", CONTROL_TOKENS),
        ("product_type", PRODUCT_TYPE_TOKENS),
        ("spout_type", SPOUT_TOKENS),
        ("trap_type", TRAP_TOKENS),
        ("shape", SHAPE_TOKENS),
    ):
        allowed = set(rows[key].allowed_values or [])
        derived = {value for _, value in table}
        assert derived <= allowed, f"{key} derives values the registry does not list: {derived - allowed}"


def test_every_enum_value_can_be_reached_by_a_customer_phrase(db):
    """An allowed value with no synonym is a value nobody can ask for."""
    seed_spec_registry(db)
    for key, row in _keys(db).items():
        if row.data_type != "enum" or not row.allowed_values:
            continue
        missing = [v for v in row.allowed_values if not (row.synonyms or {}).get(v)]
        assert missing == [], f"{key} values with no synonym: {missing}"


# --------------------------------------------------------------------------- #
# #100 user-editable, without losing the anti-drift guarantee
# --------------------------------------------------------------------------- #
def test_a_reseed_does_not_touch_a_user_owned_row(db):
    """The whole point of the `source` flag.

    The seed REPAIRS drift on every deploy so the ranker and the n8n parser cannot
    disagree about what a value is called. Applied to a row a human owns, that same
    behaviour silently reverts their edit — the UI would be a lie.
    """
    from app.models.product_spec import ProductSpecRegistry

    seed_spec_registry(db)
    db.add(
        ProductSpecRegistry(
            spec_key="zzt_custom",
            label="Mine",
            data_type="enum",
            allowed_values=["a"],
            synonyms={},
            user_synonyms={"a": ["ay"]},
            source="user",
        )
    )
    db.flush()

    seed_spec_registry(db)

    row = _keys(db)["zzt_custom"]
    assert row.label == "Mine"
    assert row.user_synonyms == {"a": ["ay"]}


def test_a_reseed_still_repairs_a_seeded_row(db):
    seed_spec_registry(db)
    row = _keys(db)["mounting"]
    row.allowed_values = ["nonsense"]
    row.source = "seed"
    db.flush()

    seed_spec_registry(db)

    assert "wall_hung" in _keys(db)["mounting"].allowed_values


def test_user_words_are_added_to_the_shipped_ones_never_replacing_them(db):
    """Additive on purpose: a staff edit must not remove a word the parser relies on."""
    from app.services.product_spec_registry import merged_synonyms

    seed_spec_registry(db)
    row = _keys(db)["mounting"]
    shipped = list(row.synonyms["wall_hung"])
    row.user_synonyms = {"wall_hung": ["hang on the wall lah"]}
    db.flush()

    merged = merged_synonyms(row)

    assert "hang on the wall lah" in merged["wall_hung"]
    for word in shipped:
        assert word in merged["wall_hung"]
    # The seed-owned column itself is untouched, so the next deploy repairs cleanly.
    assert "hang on the wall lah" not in row.synonyms["wall_hung"]


def test_a_user_word_reaches_the_resolver(db):
    """An added word has to actually change what a phrase resolves to, or it is decor."""
    from app.services.product_spec_search import resolve_terms_to_specs

    seed_spec_registry(db)
    row = _keys(db)["mounting"]
    row.user_synonyms = {"wall_hung": ["gantung dinding"]}
    db.flush()

    resolved = {e["key"]: e["value"] for e in resolve_terms_to_specs(db, ["wc gantung dinding"])}

    assert resolved.get("mounting") == "wall_hung"


# --------------------------------------------------------------------------- #
# a rule may only produce a value the key actually has (#103)
# --------------------------------------------------------------------------- #
def test_a_rule_pointing_at_a_value_the_key_does_not_have_is_refused():
    """Someone aimed a mounting rule at `free_standing`, which is not a mounting value.

    Saved silently, the next catalogue read would have written a value the ranker can
    never match, and search would have quietly got worse with nothing to point at.
    """
    from app.api.v1.master_data.spec_registry import _validate_rules

    with pytest.raises(Exception) as excinfo:
        _validate_rules(
            [{"match": "contains", "pattern": "FREE STANDING", "value": "free_standing"}],
            allowed_values=["wall_hung", "floor_standing", "pedestal"],
            data_type="enum",
        )

    assert "free_standing" in str(excinfo.value)


def test_an_open_vocabulary_key_accepts_any_value():
    # `brand` and `class` take their values from the catalogue, so there is no list to
    # check a rule against.
    from app.api.v1.master_data.spec_registry import _validate_rules

    cleaned = _validate_rules(
        [{"match": "contains", "pattern": "ACME", "value": "Acme"}],
        allowed_values=[],
        data_type="enum",
    )

    assert cleaned[0]["value"] == "Acme"


# --------------------------------------------------------------------------- #
# staff can extend a shipped key's values (#104)
# --------------------------------------------------------------------------- #
def test_a_value_staff_added_is_usable_in_a_rule(db):
    """"Add the value to this specification first" has to be possible to follow.

    A shipped key's `allowed_values` is the parser's contract and is seed-repaired, so
    it cannot be edited — which left the rejection message pointing at a door with no
    handle for every key except the ones staff made themselves.
    """
    from app.api.v1.master_data.spec_registry import _validate_rules
    from app.models.product_spec import ProductSpecRegistry
    from app.services.product_spec_registry import merged_allowed_values

    seed_spec_registry(db)
    row = db.query(ProductSpecRegistry).filter_by(spec_key="mounting").one()
    row.user_values = ["free_standing"]
    db.flush()

    assert "free_standing" in merged_allowed_values(row)
    assert "floor_standing" in merged_allowed_values(row), "the shipped list survives"

    cleaned = _validate_rules(
        [{"match": "contains", "pattern": "FREE STANDING", "value": "free_standing"}],
        allowed_values=merged_allowed_values(row),
        data_type="enum",
    )
    assert cleaned[0]["value"] == "free_standing"


def test_a_re_seed_does_not_remove_a_value_staff_added(db):
    # The whole reason `allowed_values` is locked is that the seed repairs it. An
    # additive column has to survive that, or this is the same dead end with more steps.
    from app.models.product_spec import ProductSpecRegistry

    seed_spec_registry(db)
    row = db.query(ProductSpecRegistry).filter_by(spec_key="mounting").one()
    row.user_values = ["free_standing"]
    db.flush()

    seed_spec_registry(db)

    assert db.query(ProductSpecRegistry).filter_by(spec_key="mounting").one().user_values == [
        "free_standing"
    ]


# --------------------------------------------------------------------------- #
# reviewing what a key actually did (#106)
# --------------------------------------------------------------------------- #
def _catalogue(db):
    """Two kitchen sinks and a jacuzzi, derived through the real pipeline."""
    import uuid as _uuid
    from decimal import Decimal

    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
    from app.services.product_class_signal import backfill_category_signals
    from app.services.product_spec_derivation import derive_for_code

    cat = ProductCategory(id=str(_uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS")
    uom = UnitOfMeasure(id=str(_uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
    brand = Brand(id=str(_uuid.uuid4()), brand_code="ZZT-SRT", brand_name="SORENTO")
    db.add_all([cat, uom, brand])
    db.flush()
    backfill_category_signals(db)
    seed_spec_registry(db)
    for code, description in [
        ("ZZT-RV-1", "SORENTO S/STEEL KITCHEN SINK WITH DRAINER"),
        ("ZZT-RV-2", "SORENTO S/STEEL KITCHEN SINK"),
    ]:
        db.add(
            Product(
                id=str(_uuid.uuid4()),
                product_code=code,
                product_name=code,
                description=description,
                category_id=cat.id,
                base_uom_id=uom.id,
                brand_id=brand.id,
                list_price=Decimal("1.00"),
            )
        )
        db.flush()
        derive_for_code(db, code)
    db.commit()


def test_a_key_lists_the_products_carrying_it_with_the_words_it_read(client, db):
    """A count says something happened without saying to what.

    "Seen in 106" is not reviewable: the only way to know a rule did what you meant is
    to look at the rows and the words each value was read from.
    """
    _catalogue(db)

    body = client.get(f"{ENDPOINT}/has_drainer/products").json()

    assert body["total"] == 1
    row = body["products"][0]
    assert row["product_code"] == "ZZT-RV-1"
    assert row["value"] is True
    assert row["evidence"] == "DRAINER"
    assert row["source"] == "derived"


def test_the_tallies_group_the_key_by_class_so_a_wrong_scope_is_visible(client, db):
    # `has_drainer` on 74 bathtubs is obvious in a tally and invisible in a page of rows.
    _catalogue(db)

    body = client.get(f"{ENDPOINT}/has_drainer/products").json()

    assert body["by_class"] == [{"class": "Kitchen Sink", "count": 1}]
    assert body["by_value"] == [{"value": "true", "count": 1}]


def test_an_unknown_key_is_a_404_not_an_empty_list(client, db):
    _catalogue(db)

    assert client.get(f"{ENDPOINT}/not_a_key/products").status_code == 404


def test_coverage_reports_the_live_count_not_the_note_from_when_the_key_was_written(client, db):
    """`measured_coverage` is a figure from the past; this is the catalogue now."""
    _catalogue(db)

    body = client.get(f"{ENDPOINT}/coverage").json()["coverage"]

    assert body["class"] == 2
    assert body["has_drainer"] == 1


# --------------------------------------------------------------------------- #
# taking a shipped word away (#109)
# --------------------------------------------------------------------------- #
def test_a_shipped_synonym_can_be_suppressed(client, db):
    """"matte black" ships as a word for `black`, and it is a colour in its own right.

    Adding a `matte_black` value does not help while the word still resolves to
    `black` first, and editing the seed row is undone on the next deploy. Suppression
    is the only honest way to say "this business does not use that word for that".
    """
    seed_spec_registry(db)

    body = client.patch(
        f"{ENDPOINT}/finish",
        json={"suppressed_synonyms": {"black": ["matte black"]}},
    ).json()

    assert "matte black" not in body["synonyms"]["black"]
    assert "black" in body["synonyms"]["black"], "only the named word goes"
    assert "matt black" in body["synonyms"]["black"], "and only that spelling of it"


def test_suppression_survives_a_re_seed(client, db):
    # The seed repairs `synonyms` on every deploy. If suppression did not outlive that,
    # the word would come back and the setting would look like it never saved.
    seed_spec_registry(db)
    client.patch(f"{ENDPOINT}/finish", json={"suppressed_synonyms": {"black": ["matte black"]}})

    seed_spec_registry(db)

    row = _keys(db)["finish"]
    assert "matte black" not in merged_synonyms(row)["black"]


def test_un_suppressing_puts_the_word_back(client, db):
    # Nothing is deleted, so this is reversible - which is what makes it safe to try.
    seed_spec_registry(db)
    client.patch(f"{ENDPOINT}/finish", json={"suppressed_synonyms": {"black": ["matte black"]}})

    body = client.patch(f"{ENDPOINT}/finish", json={"suppressed_synonyms": {}}).json()

    assert "matte black" in body["synonyms"]["black"]


def test_suppressing_a_second_word_keeps_the_first_suppressed(client, db):
    """The editor sends the WHOLE suppression list, not the delta it just made.

    `synonyms` comes back merged, with earlier suppressions already applied, so an
    editor that computed "what did I remove this time" from it could not see them and
    left them out of the payload - which reinstated them. From the screen that read as
    "I deleted the word, came back, and it is still there", because a different word
    with almost the same spelling had quietly returned.
    """
    seed_spec_registry(db)
    client.patch(f"{ENDPOINT}/finish", json={"suppressed_synonyms": {"black": ["matte black"]}})

    body = client.patch(
        f"{ENDPOINT}/finish",
        json={"suppressed_synonyms": {"black": ["matte black", "matt black"]}},
    ).json()

    assert body["synonyms"]["black"] == ["black"]
    assert set(body["suppressed_synonyms"]["black"]) == {"matte black", "matt black"}


# --------------------------------------------------------------------------- #
# taking a shipped VALUE away
# --------------------------------------------------------------------------- #
def test_a_shipped_value_can_be_taken_away_and_put_back(client, db):
    """`user_values` could only ever add, so a shipped value was permanent.

    A business that does not sell french gold had no way to stop the ranker offering
    it: the chip rendered locked, with no remove control and nothing explaining why.
    """
    seed_spec_registry(db)

    body = client.patch(
        f"{ENDPOINT}/finish", json={"suppressed_values": ["french_gold"]}
    ).json()
    assert "french_gold" not in body["allowed_values"]
    assert body["suppressed_values"] == ["french_gold"]

    back = client.patch(f"{ENDPOINT}/finish", json={"suppressed_values": []}).json()
    assert "french_gold" in back["allowed_values"], "nothing was deleted, so it returns"


def test_suppressing_a_value_stops_it_being_derived(client, db):
    """Suppression has to stop the value being PRODUCED, not merely offered.

    Left at "not offered", the catalogue keeps filling in a value the business has said
    it does not use, and every product carrying it still ranks for it.
    """
    from app.services.product_spec_derivation import configured_rules

    seed_spec_registry(db)
    before = configured_rules(db)
    assert any(
        str(rule.get("value")) == "french_gold" for rule in before.get("finish", [])
    ), "a rule produces this value to begin with, or the test proves nothing"

    client.patch(f"{ENDPOINT}/finish", json={"suppressed_values": ["french_gold"]})

    after = configured_rules(db)
    assert not any(str(rule.get("value")) == "french_gold" for rule in after.get("finish", []))
    assert after.get("finish"), "only that value's rules go, not the whole key's"


def test_a_rule_survives_the_value_it_produces_being_suppressed(client, db):
    """Taking a value away must not invalidate somebody's rule.

    Rules are validated against the vocabulary, so the strict reading rejected the whole
    save with a 400 the moment a value a rule mentions was suppressed - which made
    removing a value impossible for exactly the values that were in use.
    """
    seed_spec_registry(db)
    client.patch(f"{ENDPOINT}/finish", json={"suppressed_values": ["french_gold"]})

    response = client.patch(
        f"{ENDPOINT}/finish",
        json={"derivation_rules": [{"match": "contains", "pattern": "FR GOLD", "value": "french_gold"}]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["derivation_rules"][0]["value"] == "french_gold"


def test_a_release_can_correct_a_rule_it_shipped(db):
    """The seed must be able to fix its own mistake, not only add to it.

    This is not hypothetical: `has_fixing_screw` matched the bare noun SCREW, so a
    basin described "**W/O SCREW" - sold WITHOUT one - derived yes. Correcting the
    pattern put the fixed rule NEXT TO the broken one, first-match-wins kept firing
    the broken one, and the fix was invisible.
    """
    seed_spec_registry(db, commit=False)
    row = _keys(db)["has_fixing_screw"]

    # Pretend the release before this one shipped the broken pattern, and that a human
    # added a rule of their own on top.
    row.derivation_rules = [
        {"match": "present", "pattern": "SCREW", "value": True, "_seed": True},
        {"match": "present", "pattern": "MOUNTING KIT", "value": True},
    ]
    db.flush()

    seed_spec_registry(db, commit=False)
    rules = _keys(db)["has_fixing_screw"].derivation_rules
    patterns = [r["pattern"] for r in rules]

    assert "SCREW" not in patterns, "the superseded seed rule survived and still fires first"
    assert any("W/O" in p for p in patterns), "the corrected rule was not installed"
    assert "MOUNTING KIT" in patterns, "a human's own rule must never be removed by a seed"
