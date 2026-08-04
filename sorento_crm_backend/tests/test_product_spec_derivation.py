"""Turn catalog text into structured specs, deterministically.

No inference lives here, and that is the point. Two derivation mechanisms were signed
off and then measured false: curating specs out of the description (bowl count appears
in 110 of 22,366 descriptions, thickness in 136) and inducing dimensions from code
conventions (best rule 25.3% against 387 labelled rows, needing 99%). What survives is
what can be read directly: existing columns, literal description tokens, and closed
code lookups. See PLAN-spec-search.md section 2.

The hardest case is shape. A round basin has a diameter, `products` cannot express
one, and the data has been forced into L/W/H anyway:

    CONCRETE ROUND BASIN (407X120X10MM)  ->  length=407 width=120 height=10
                                              ^ diameter ^ depth  ^ thickness

231 codes have length = width, the fingerprint of a round or square product stored as
rectangular. Ranking "600mm wide basin" against one of those returns nonsense today.

Ticket: jayson-odoo/sorento-crm#74. Contract:
documentation/plans/products/spec-search-acceptance-criteria.md AC-T0c-01 .. AC-T0c-21.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.company import Company
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecException
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_all, derive_for_code
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        _fixtures(s)
        yield s


_REFS: dict = {}


def _fixtures(db):
    """Category, brand and UOM every product row needs to exist at all."""
    cat = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS")
    cat_wb = ProductCategory(id=str(uuid.uuid4()), category_code="CB-KS", category_name="CB-KS")
    misc = ProductCategory(id=str(uuid.uuid4()), category_code="SRTPART", category_name="SRTPART")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
    brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-SRT", brand_name="Sorento")
    # A second company, because product_code is unique PER COMPANY: the live catalog
    # holds every model twice, once per company, which is exactly what the fan-out
    # test needs to exercise.
    second = Company(id=str(uuid.uuid4()), name="ZZT Second Co", code="ZZT2")
    db.add_all([cat, cat_wb, misc, uom, brand, second])
    db.flush()
    backfill_category_signals(db)
    _REFS.update(
        {
            "cat": cat.id,
            "cat_wb": cat_wb.id,
            "misc": misc.id,
            "uom": uom.id,
            "brand": brand.id,
            "company2": second.id,
        }
    )


def _product(
    db,
    code: str,
    description: str,
    *,
    category=None,
    length=None,
    width=None,
    height=None,
    company_id=None,
) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS[category or "cat"],
        base_uom_id=_REFS["uom"],
        list_price=Decimal("1.00"),
        dimensions_length=length,
        dimensions_width=width,
        dimensions_height=height,
    )
    if company_id is not None:
        row.company_id = company_id
    db.add(row)
    db.flush()
    return row


def _specs(db, code: str) -> dict:
    row = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == code)
        .first()
    )
    return row.values if row else {}


def _value(db, code: str, key: str):
    entry = _specs(db, code).get(key)
    return entry.get("value") if entry else None


def _exceptions(db, code: str) -> set[str]:
    return {
        r.reason
        for r in db.query(ProductSpecException).filter(ProductSpecException.product_code == code).all()
    }


# --------------------------------------------------------------------------- #
# class and brand, straight off the category (AC-T0c-03)
# --------------------------------------------------------------------------- #
def test_class_and_brand_come_from_the_category(db):
    _product(db, "ZZT-KS-1", "SORENTO S/STEEL KITCHEN SINK")
    derive_for_code(db, "ZZT-KS-1")

    assert _value(db, "ZZT-KS-1", "class") == "Kitchen Sink"
    assert _value(db, "ZZT-KS-1", "brand") == "Sorento"


# --------------------------------------------------------------------------- #
# shape (AC-T0c-03)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "description,expected",
    [
        ("SORENTO ROUND WASH BASIN", "round"),
        ("SORENTO SQUARE WASH BASIN", "square"),
        ("SORENTO SQ WASH BASIN", "square"),
        ("SORENTO OVAL WASH BASIN", "oval"),
    ],
)
def test_shape_is_read_from_the_description(db, description, expected):
    _product(db, "ZZT-SHAPE", description)
    derive_for_code(db, "ZZT-SHAPE")
    assert _value(db, "ZZT-SHAPE", "shape") == expected


def test_shape_is_left_null_when_unstated(db):
    # NOT defaulted to rectangular. An unstated shape is unknown, and the dimension
    # rules below depend on telling those two apart.
    _product(db, "ZZT-NOSHAPE", "SORENTO S/STEEL KITCHEN SINK")
    derive_for_code(db, "ZZT-NOSHAPE")
    assert _value(db, "ZZT-NOSHAPE", "shape") is None


# --------------------------------------------------------------------------- #
# the round-basin bug (AC-T0c-04, AC-T0c-05)
# --------------------------------------------------------------------------- #
def test_round_product_yields_a_diameter_not_a_width(db):
    _product(db, "ZZT-ROUND", "CONCRETE ROUND BASIN WITH CLICK VALVE (407X120X10MM)")
    derive_for_code(db, "ZZT-ROUND")

    assert _value(db, "ZZT-ROUND", "shape") == "round"
    assert _value(db, "ZZT-ROUND", "diameter") == 407
    assert _value(db, "ZZT-ROUND", "depth") == 120
    assert _value(db, "ZZT-ROUND", "thickness") == 10
    assert _value(db, "ZZT-ROUND", "dim_length") is None
    assert _value(db, "ZZT-ROUND", "dim_width") is None


def test_square_product_also_yields_a_diameter(db):
    _product(db, "ZZT-SQ", "SORENTO SQUARE ART BASIN (400X400X140MM)")
    derive_for_code(db, "ZZT-SQ")
    assert _value(db, "ZZT-SQ", "diameter") == 400


def test_round_product_with_stored_rectangular_columns_is_flagged(db):
    # The stored columns are mis-keyed for a round product: 407 is a diameter, not a
    # length. Derivation must not trust them, and a human must be told.
    _product(
        db,
        "ZZT-ROUND-COLS",
        "CONCRETE ROUND BASIN (407X120X10MM)",
        length=Decimal("407"),
        width=Decimal("120"),
        height=Decimal("10"),
    )
    derive_for_code(db, "ZZT-ROUND-COLS")

    assert _value(db, "ZZT-ROUND-COLS", "diameter") == 407
    assert _value(db, "ZZT-ROUND-COLS", "dim_length") is None
    assert "shape_mismatch" in _exceptions(db, "ZZT-ROUND-COLS")


# AC-T0c-06: length == width is the fingerprint of a round or square product forced
# into rectangular columns, even when the description never says so.
def test_equal_length_and_width_is_flagged_as_a_shape_mismatch(db):
    _product(
        db,
        "ZZT-EQ",
        "SORENTO ART BASIN",
        length=Decimal("440"),
        width=Decimal("440"),
        height=Decimal("140"),
    )
    derive_for_code(db, "ZZT-EQ")
    assert "shape_mismatch" in _exceptions(db, "ZZT-EQ")


# --------------------------------------------------------------------------- #
# rectangular dimensions (AC-T0c-07, AC-T0c-08, AC-T0c-09)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "description",
    [
        "CABANA KITCHEN SINK (1000X500X140MM)",
        "CABANA KITCHEN SINK (1000 X 500 X 140MM)",
        "CABANA KITCHEN SINK 1000x500x140mm",
        "CABANA KITCHEN SINK (SIZE : 1000 X 500 X 140MM)",
        "CABANA KITCHEN SINK 1000*500*140MM",
    ],
)
def test_dimension_triple_is_parsed_in_every_written_form(db, description):
    _product(db, "ZZT-DIM", description)
    derive_for_code(db, "ZZT-DIM")

    assert _value(db, "ZZT-DIM", "dim_length") == 1000
    assert _value(db, "ZZT-DIM", "dim_width") == 500
    assert _value(db, "ZZT-DIM", "dim_height") == 140


def test_dimension_quad_yields_thickness(db):
    _product(db, "ZZT-QUAD", "SORENTO S/STEEL KITCHEN SINK (798X500X220X1.2MM)")
    derive_for_code(db, "ZZT-QUAD")

    assert _value(db, "ZZT-QUAD", "dim_length") == 798
    assert _value(db, "ZZT-QUAD", "thickness") == 1.2


def test_stored_columns_win_over_the_description(db):
    _product(
        db,
        "ZZT-CONFLICT",
        "CABANA KITCHEN SINK (1000X500X140MM)",
        length=Decimal("999"),
        width=Decimal("500"),
        height=Decimal("140"),
    )
    derive_for_code(db, "ZZT-CONFLICT")

    assert _value(db, "ZZT-CONFLICT", "dim_length") == 999
    assert "column_conflict" in _exceptions(db, "ZZT-CONFLICT")


def test_description_fills_a_dimension_the_columns_lack(db):
    _product(db, "ZZT-FILL", "CABANA KITCHEN SINK (1000X500X140MM)")
    derive_for_code(db, "ZZT-FILL")
    assert _value(db, "ZZT-FILL", "dim_length") == 1000


def test_no_dimensions_anywhere_writes_nothing(db):
    # A NULL spec is a correct answer. It leaves the row to the other ranking legs,
    # where a guessed one would actively boost a wrong candidate.
    _product(db, "ZZT-NODIM", "SORENTO KITCHEN SINK")
    derive_for_code(db, "ZZT-NODIM")
    assert _value(db, "ZZT-NODIM", "dim_length") is None


# --------------------------------------------------------------------------- #
# material, mounting, control type (AC-T0c-10, 11, 13)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "description,expected",
    [
        ("SORENTO S/STEEL KITCHEN SINK", "stainless_steel"),
        ("SORENTO STAINLESS STEEL SINK", "stainless_steel"),
        ("SORENTO CERAMIC WASH BASIN", "ceramic"),
        ("SORENTO TEMPERED GLASS BASIN", "glass"),
        ("SORENTO PVC BOTTLE TRAP", "pvc"),
        ("SORENTO BRASS ANGLE VALVE", "brass"),
        ("SORENTO ACRYLIC BATHTUB", "acrylic"),
    ],
)
def test_material_is_read_from_the_description(db, description, expected):
    _product(db, "ZZT-MAT", description)
    derive_for_code(db, "ZZT-MAT")
    assert _value(db, "ZZT-MAT", "material") == expected


@pytest.mark.parametrize(
    "description,expected",
    [
        ("SORENTO WALL HUNG WATER CLOSET", "wall_hung"),
        ("SORENTO WALL MOUNTED BASIN", "wall_hung"),
        ("SORENTO FLOOR STANDING WATER CLOSET", "floor_standing"),
        ("SORENTO BASIN WITH PEDESTAL", "pedestal"),
        ("SORENTO CONCEALED CISTERN", "concealed"),
        ("SORENTO COUNTER TOP BASIN", "counter_top"),
    ],
)
def test_mounting_is_read_from_the_description(db, description, expected):
    _product(db, "ZZT-MOUNT", description)
    derive_for_code(db, "ZZT-MOUNT")
    assert _value(db, "ZZT-MOUNT", "mounting") == expected


@pytest.mark.parametrize(
    "description,expected",
    [
        ("SORENTO BASIN MIXER TAP", "mixer"),
        ("SORENTO PILLAR TAP", "pillar"),
        ("CABANA HOSE BIB TAP", "bib"),
        ("SORENTO SINGLE LEVER BASIN TAP", "single_lever"),
    ],
)
def test_control_type_is_read_from_the_description(db, description, expected):
    _product(db, "ZZT-CTRL", description)
    derive_for_code(db, "ZZT-CTRL")
    assert _value(db, "ZZT-CTRL", "control_type") == expected


# --------------------------------------------------------------------------- #
# finish, from the code suffix (AC-T0c-12)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "code,expected",
    [
        ("ZZTKS1050-BL", "black"),
        ("ZZTKS1050-GM", "gunmetal"),
        ("ZZTKS1050-NL", "nickel"),
        ("ZZTKS1050-RG", "rose_gold"),
        ("ZZTKS1050-CR", "chrome"),
    ],
)
def test_finish_comes_from_the_code_suffix(db, code, expected):
    _product(db, code, "CABANA KITCHEN SINK")
    derive_for_code(db, code)
    assert _value(db, code, "finish") == expected


@pytest.mark.parametrize("code", ["ZZTKS1050-DIY", "ZZTKS1050-ENG", "ZZTKS1050-NEW", "ZZTKS1050-1"])
def test_non_finish_suffixes_yield_nothing(db, code):
    # DIY is packaging, ENG is the -P-ENG collision family, bare digits are variant
    # numbering. None of them is a colour.
    _product(db, code, "CABANA KITCHEN SINK")
    derive_for_code(db, code)
    assert _value(db, code, "finish") is None


# --------------------------------------------------------------------------- #
# accessory discriminator (AC-T0c-14)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "code,description,category",
    [
        ("ACC-ZZT001", "CABANA KITCHEN SINK TRIANGLE BASKET", None),
        ("ZZT-DRAINER", "S/STEEL KITCHEN SINK DRAINER (440X200X100MM)", None),
        ("ZZT-TAIL", "300MM TAIL PIPE FOR 40MM BOTTLE TRAP", None),
        ("ZZT-ONLY", "SORENTO BATHTUB WASTE ONLY", None),
        ("ZZT-SPARE", "SPARE SEAT COVER USED FOR ZZTWC6015", None),
        ("ZZT-PART", "SORENTO KITCHEN SINK", "misc"),
    ],
)
def test_accessories_are_flagged(db, code, description, category):
    _product(db, code, description, category=category)
    derive_for_code(db, code)
    assert _value(db, code, "is_accessory") is True


# Real catalog data caught this: 22 kitchen sinks were flagged accessories on the word
# DRAINER alone. A sink with a drainer board is a sink.
@pytest.mark.parametrize(
    "code,description",
    [
        ("ZZT-FEAT1", "CABANA KITCHEN SINK (1000 X 500 X 140MM) -1 BOWL 1 DRAINER-"),
        ("ZZT-FEAT2", "SORENTO KITCHEN SINK C/W BASKET"),
        ("ZZT-FEAT3", "SORENTO WASH BASIN WITH WASTE"),
        ("ZZT-FEAT4", "SORENTO KITCHEN SINK 2 BOWL 1 DRAINER"),
    ],
)
def test_a_noun_that_is_only_a_feature_does_not_flag_an_accessory(db, code, description):
    _product(db, code, description)
    derive_for_code(db, code)
    assert _value(db, code, "is_accessory") is False


@pytest.mark.parametrize(
    "code,description",
    [
        ("ZZT-HEAD1", "S/STEEL KITCHEN SINK DRAINER (440X200X100MM)"),
        ("ZZT-HEAD2", "CABANA KITCHEN SINK TRIANGLE BASKET"),
        ("ZZT-HEAD3", "SORENTO JACCUZI / BATHTUB OUTLET WASTE"),
    ],
)
def test_a_noun_heading_the_phrase_still_flags_an_accessory(db, code, description):
    _product(db, code, description)
    derive_for_code(db, code)
    assert _value(db, code, "is_accessory") is True


def test_a_real_product_is_not_flagged_as_an_accessory(db):
    _product(db, "ZZT-REAL", "SORENTO S/STEEL KITCHEN SINK (798X500X220MM)")
    derive_for_code(db, "ZZT-REAL")
    assert _value(db, "ZZT-REAL", "is_accessory") is False


# --------------------------------------------------------------------------- #
# provenance, fan-out, idempotency (AC-T0c-02, 15, 16, 20)
# --------------------------------------------------------------------------- #
def test_every_value_records_its_evidence(db):
    _product(db, "ZZT-EV", "SORENTO S/STEEL KITCHEN SINK (798X500X220MM)")
    derive_for_code(db, "ZZT-EV")

    row = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "ZZT-EV")
        .one()
    )
    material = row.provenance["material"]
    assert material["source"] == "derived"
    assert material["confidence"] == 1.0
    assert "S/STEEL" in material["evidence"].upper()


def test_evidence_is_literally_present_in_the_source_text(db):
    # The same gate the parser applies to customer messages, applied to the catalog:
    # a value whose evidence is not in the text is a hallucination, not a derivation.
    _product(db, "ZZT-EV2", "SORENTO CERAMIC WALL HUNG WATER CLOSET (360X520X330MM)")
    derive_for_code(db, "ZZT-EV2")

    row = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "ZZT-EV2")
        .one()
    )
    haystack = "SORENTO CERAMIC WALL HUNG WATER CLOSET (360X520X330MM) ZZT-EV2 SRT-KS Kitchen Sink Sorento"
    for key, entry in row.provenance.items():
        assert entry["evidence"].upper() in haystack.upper(), key


def test_derivation_fans_out_to_every_row_sharing_the_code(db):
    # The same model exists once per company (11,414 codes, 22,805 rows). Deriving per
    # row would let the two copies disagree with nothing detecting it. Fan-out needs
    # the all-companies scope, which is why the batch job runs unscoped.
    _product(db, "ZZT-FANOUT", "SORENTO S/STEEL KITCHEN SINK")
    _product(
        db,
        "ZZT-FANOUT",
        "SORENTO S/STEEL KITCHEN SINK",
        company_id=_REFS["company2"],
    )

    with company_scope(db, None):
        derive_for_code(db, "ZZT-FANOUT")

        rows = (
            db.query(ProductSpecifications)
            .join(Product, Product.id == ProductSpecifications.product_id)
            .filter(Product.product_code == "ZZT-FANOUT")
            .all()
        )
        assert len(rows) == 2
        assert all(r.values["material"]["value"] == "stainless_steel" for r in rows)


def test_representative_row_prefers_a_classified_category(db):
    # The company copies of a model can sit in different categories, and only some are
    # classified. Reading whichever row the database returned first dropped class and
    # brand for 40 of 594 real pilot codes, and made the output depend on row order.
    _product(db, "ZZT-MIXEDCAT", "SORENTO S/STEEL KITCHEN SINK", category="misc")
    _product(
        db,
        "ZZT-MIXEDCAT",
        "SORENTO S/STEEL KITCHEN SINK",
        category="cat",
        company_id=_REFS["company2"],
    )

    with company_scope(db, None):
        derive_for_code(db, "ZZT-MIXEDCAT")

        rows = (
            db.query(ProductSpecifications)
            .join(Product, Product.id == ProductSpecifications.product_id)
            .filter(Product.product_code == "ZZT-MIXEDCAT")
            .all()
        )
        assert len(rows) == 2
        for row in rows:
            assert row.values["class"]["value"] == "Kitchen Sink"


def test_derivation_under_a_single_company_scope_stays_in_that_company(db):
    # The service respects company isolation rather than quietly crossing it. A
    # request-time re-derive must not write specs for another company's rows; only
    # the deliberately unscoped batch job fans out.
    _product(db, "ZZT-SCOPED", "SORENTO S/STEEL KITCHEN SINK")
    _product(
        db,
        "ZZT-SCOPED",
        "SORENTO S/STEEL KITCHEN SINK",
        company_id=_REFS["company2"],
    )

    result = derive_for_code(db, "ZZT-SCOPED")

    assert result["written"] == 1


def test_rederiving_unchanged_input_is_a_no_op(db):
    _product(db, "ZZT-HASH", "SORENTO S/STEEL KITCHEN SINK")
    first = derive_for_code(db, "ZZT-HASH")
    second = derive_for_code(db, "ZZT-HASH")

    assert first["written"] == 1
    assert second["written"] == 0
    assert second["skipped"] == 1


def test_changing_the_description_rederives(db):
    row = _product(db, "ZZT-CHANGE", "SORENTO S/STEEL KITCHEN SINK")
    derive_for_code(db, "ZZT-CHANGE")

    row.description = "SORENTO CERAMIC KITCHEN SINK"
    db.flush()
    result = derive_for_code(db, "ZZT-CHANGE")

    assert result["written"] == 1
    assert _value(db, "ZZT-CHANGE", "material") == "ceramic"


def test_human_confirmed_values_survive_rederivation(db):
    row = _product(db, "ZZT-HUMAN", "SORENTO S/STEEL KITCHEN SINK")
    derive_for_code(db, "ZZT-HUMAN")

    spec = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "ZZT-HUMAN")
        .one()
    )
    spec.values = {**spec.values, "material": {"value": "brass"}}
    spec.provenance = {**spec.provenance, "material": {"source": "human", "confidence": 1.0, "evidence": "reviewed"}}
    spec.derived_hash = None          # force a re-derive
    db.flush()

    derive_for_code(db, "ZZT-HUMAN")

    assert _value(db, "ZZT-HUMAN", "material") == "brass"


# --------------------------------------------------------------------------- #
# batch (AC-T0c-18)
# --------------------------------------------------------------------------- #
def test_derive_all_reports_counts(db):
    _product(db, "ZZT-B1", "SORENTO S/STEEL KITCHEN SINK")
    _product(db, "ZZT-B2", "CABANA CERAMIC KITCHEN SINK (500X400X200MM)")

    result = derive_all(db, codes=["ZZT-B1", "ZZT-B2"])

    assert result["written"] == 2
    assert result["codes"] == 2
