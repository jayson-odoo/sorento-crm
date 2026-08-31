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
    # A brand the category prefix cannot express. 1,934 live rows sit in a SRT-*/CB-*
    # category while carrying a different brand_id, so the two really do disagree.
    other = Brand(id=str(uuid.uuid4()), brand_code="ZZT-OTH", brand_name="OTHERS")
    # A second company, because product_code is unique PER COMPANY: the live catalog
    # holds every model twice, once per company, which is exactly what the fan-out
    # test needs to exercise.
    second = Company(id=str(uuid.uuid4()), name="ZZT Second Co", code="ZZT2")
    db.add_all([cat, cat_wb, misc, uom, brand, other, second])
    db.flush()
    backfill_category_signals(db)
    _REFS.update(
        {
            "cat": cat.id,
            "cat_wb": cat_wb.id,
            "misc": misc.id,
            "uom": uom.id,
            "brand": brand.id,
            "brand_other": other.id,
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
    brand=None,
) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS[category or "cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS[brand] if brand else None,
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


def _provenance(db, code: str) -> dict:
    row = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == code)
        .first()
    )
    return row.provenance if row else {}


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
def test_the_description_names_its_own_class_and_outranks_the_category(db):
    """`SORENTO SQUATTING PAN` in an SRT-WC category is not a water closet.

    The category is the business's filing, not a description of the product, and it is
    wrong in both directions - 11 squatting pans and 6 urinals sit under Water Closet,
    120 flexible hoses under Tap. English puts the head noun last, so the description
    already carries the answer.
    """
    _product(db, "ZZT-SP-1", "SORENTO SQUATTING PAN ZZT-SP-1", brand="brand")
    derive_for_code(db, "ZZT-SP-1")

    assert _value(db, "ZZT-SP-1", "class") == "Squatting Pan"
    assert _provenance(db, "ZZT-SP-1")["class"]["evidence"] == "SQUATTING PAN"


def test_only_a_trailing_noun_names_the_class(db):
    # An earlier class word is a modifier saying what the product is FOR. Reading it as
    # the class made `URINAL FLUSH VALVE` a urinal and `BASIN MIXER` a wash basin.
    _product(db, "ZZT-UFV-1", "CABANA URINAL FLUSH VALVE ZZT-UFV-1", brand="brand")
    derive_for_code(db, "ZZT-UFV-1")

    assert _value(db, "ZZT-UFV-1", "class") == "Kitchen Sink", "falls back to the category"


def test_what_a_product_comes_with_does_not_name_its_class(db):
    # 61 taps were reclassified by their accessories before this cut existed.
    _product(db, "ZZT-KT-1", "SORENTO KITCHEN MIXER TAP WITH PULL OUT SHOWER ZZT-KT-1", brand="brand")
    derive_for_code(db, "ZZT-KT-1")

    assert _value(db, "ZZT-KT-1", "class") == "Tap"


def test_class_comes_from_the_category_and_brand_from_the_product(db):
    _product(db, "ZZT-KS-1", "SORENTO S/STEEL KITCHEN SINK", brand="brand")
    derive_for_code(db, "ZZT-KS-1")

    assert _value(db, "ZZT-KS-1", "class") == "Kitchen Sink"
    assert _value(db, "ZZT-KS-1", "brand") == "Sorento"


def test_the_products_own_brand_beats_the_category_prefix(db):
    """`SRT-KS` decodes to Sorento; the product says OTHERS. Curated data wins.

    Reading brand off the prefix mislabelled 1,934 of 20,515 live rows - every
    INFINITY, OTHERS and NO LOGO product was published as Sorento or Cabana, and four
    brands the prefix cannot spell at all were unreachable by a brand search.
    """
    _product(db, "ZZT-KS-BRAND", "S/STEEL KITCHEN SINK", brand="brand_other")
    derive_for_code(db, "ZZT-KS-BRAND")

    assert _value(db, "ZZT-KS-BRAND", "brand") == "OTHERS"
    assert _value(db, "ZZT-KS-BRAND", "class") == "Kitchen Sink", "class still comes off the category"


def test_a_product_with_no_brand_gets_no_brand(db):
    """34 live rows. The prefix is not used as a fallback.

    It is the same decode that mislabelled 1,934 rows, and it spells brands its own way
    ("Sorento" against the brands table's "SORENTO"), which would put two spellings of
    one brand into an open vocabulary and split the ranker's evidence between them.
    """
    _product(db, "ZZT-KS-NOBRAND", "S/STEEL KITCHEN SINK")
    derive_for_code(db, "ZZT-KS-NOBRAND")

    assert _value(db, "ZZT-KS-NOBRAND", "brand") is None
    assert _value(db, "ZZT-KS-NOBRAND", "class") == "Kitchen Sink"


def test_company_copies_with_different_brands_are_flagged(db):
    """One derivation per CODE, but brand lives on the ROW. 6 live rows disagree.

    Both copies get the chosen brand, so one of them is wrong; the exception is the only
    thing that says so.
    """
    _product(db, "ZZT-KS-SPLIT", "S/STEEL KITCHEN SINK", brand="brand")
    _product(
        db,
        "ZZT-KS-SPLIT",
        "S/STEEL KITCHEN SINK",
        brand="brand_other",
        company_id=_REFS["company2"],
    )
    # All-companies scope, same as the batch job: that is what makes both copies
    # visible to one derivation, and therefore what makes the disagreement detectable.
    with company_scope(db, None):
        derive_for_code(db, "ZZT-KS-SPLIT")

        assert "company_copies_disagree" in _exceptions(db, "ZZT-KS-SPLIT")


def test_a_rebrand_re_derives(db):
    """The hash gates the whole catalog run; a brand it ignores is a silent stale row."""
    row = _product(db, "ZZT-KS-REBRAND", "S/STEEL KITCHEN SINK", brand="brand_other")
    derive_for_code(db, "ZZT-KS-REBRAND")
    assert _value(db, "ZZT-KS-REBRAND", "brand") == "OTHERS"

    row.brand_id = _REFS["brand"]
    db.flush()
    derive_for_code(db, "ZZT-KS-REBRAND")

    assert _value(db, "ZZT-KS-REBRAND", "brand") == "Sorento"


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
        ("SORENTO SINGLE LEVER BASIN TAP", "single_lever"),
        ("CABANA TWO WAY TAP", "two_way"),
        ("SORENTO SELF CLOSING BASIN TAP", "self_closing"),
        ("SORENTO WALL HUNG URINAL C/W SENSOR", "sensor"),
    ],
)
def test_control_type_is_read_from_the_description(db, description, expected):
    _product(db, "ZZT-CTRL", description)
    derive_for_code(db, "ZZT-CTRL")
    assert _value(db, "ZZT-CTRL", "control_type") == expected


@pytest.mark.parametrize(
    "description,key,expected",
    [
        # These three used to be control types. They are not: two name the product and
        # one names where it is fixed. Holding them under `control_type` let a single
        # product score the same fact twice, on two different legs of the ranker.
        ("SORENTO BASIN MIXER TAP", "product_type", "mixer_tap"),
        ("CABANA HOSE BIB TAP", "product_type", "bib_tap"),
        ("SORENTO PILLAR TAP", "mounting", "pillar_mounted"),
    ],
)
def test_product_nouns_and_mounting_are_not_control_types(db, description, key, expected):
    _product(db, "ZZT-CTRL2", description)
    derive_for_code(db, "ZZT-CTRL2")
    assert _value(db, "ZZT-CTRL2", key) == expected
    assert _value(db, "ZZT-CTRL2", "control_type") is None


# --------------------------------------------------------------------------- #
# what the first real user report asked for: bowls, taps, features
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "description,expected",
    [
        ("SORENTO S/STEEL SINGLE BOWL WITH DRAINER SINK 860X500X200MM", 1),
        ("MOCHA KITCHEN SINK (DOUBLE BOWL). MKS8644", 2),
        ("CABANA KITCHEN SINK CKS1050 -1 BOWL 1 DRAINER-", 1),
        ("CABANA KITCHEN SINK -2 BOWLS-", 2),
        ("SORENTO TRIPLE BOWL SINK", 3),
    ],
)
def test_bowl_count_is_read_where_the_description_states_it(db, description, expected):
    _product(db, "ZZT-BOWL", description)
    derive_for_code(db, "ZZT-BOWL")
    assert _value(db, "ZZT-BOWL", "bowl_count") == expected


def test_bowl_count_is_never_guessed_from_a_length(db):
    """The 90% case. A 1000 mm sink is not evidence of two bowls.

    Inferring it would put single-bowl sinks in front of a customer who asked for a
    double, which is worse than returning nothing: they can see a wrong answer but not
    a missing one.
    """
    _product(db, "ZZT-NOBOWL", "CABANA KITCHEN SINK (SIZE : 1000 X 500 X 140MM)")
    derive_for_code(db, "ZZT-NOBOWL")
    assert _value(db, "ZZT-NOBOWL", "bowl_count") is None




@pytest.mark.parametrize(
    "description,key,expected",
    [
        # The three phrases the first user report said returned nothing useful.
        ("SORENTO WALL MOUNTED FLEXIBLE HEAD + S/STEEL SPOUT KITCHEN TAP", "mounting", "wall_hung"),
        ("SORENTO WALL MOUNTED FLEXIBLE HEAD + S/STEEL SPOUT KITCHEN TAP", "spout_type", "flexible"),
        (
            "SORENTO WALL MOUNTED FLEXIBLE HEAD + S/STEEL SPOUT KITCHEN TAP",
            "material",
            "stainless_steel",
        ),
        ("CABANA PILLAR MOUNTED KITCHEN TAP", "mounting", "pillar_mounted"),
        ("CABANA PILLAR MOUNTED FLEXIBLE KITCHEN TAP", "spout_type", "flexible"),
        ("BRAVAT ANGLE VALVE P6605C", "product_type", "angle_valve"),
        ("SORENTO CLOSE-COUPLED WATER CLOSET (S-TRAP)", "trap_type", "s_trap"),
        ("SORENTO CLOSE COUPLED PEDESTAL ONLY (P-TRAP)", "trap_type", "p_trap"),
    ],
)
def test_tap_vocabulary_is_read_from_the_description(db, description, key, expected):
    _product(db, "ZZT-TAPV", description)
    derive_for_code(db, "ZZT-TAPV")
    assert _value(db, "ZZT-TAPV", key) == expected


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
# seat_material, from the code as a fallback (PLAN-flyer-family-proposals.md S1
# measurement, 31 Aug 2026: one live `-UF` product carries no description at all)
# --------------------------------------------------------------------------- #
def test_seat_material_falls_back_to_the_code_when_the_description_is_silent(db):
    _product(db, "ZZTWC-CODEUF-UF", "SORENTO ONE PIECE WC")
    derive_for_code(db, "ZZTWC-CODEUF-UF")
    assert _value(db, "ZZTWC-CODEUF-UF", "seat_material") == "uf"


def test_seat_material_from_the_description_beats_the_code(db):
    """The code says UF; the description says DUROPLAST. Words win (source-major)."""
    _product(db, "ZZTWC-CODEUF-DUR-UF", "SORENTO ONE PIECE WC DUROPLAST SEAT COVER")
    derive_for_code(db, "ZZTWC-CODEUF-DUR-UF")
    assert _value(db, "ZZTWC-CODEUF-DUR-UF", "seat_material") == "duroplast"


# --------------------------------------------------------------------------- #
# accessory discriminator (AC-T0c-14)
# --------------------------------------------------------------------------- #


# Real catalog data caught this: 22 kitchen sinks were flagged accessories on the word
# DRAINER alone. A sink with a drainer board is a sink.






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


def test_a_rule_change_invalidates_a_cached_derivation(db, monkeypatch):
    """The skip-if-unchanged cache must key on the RULES, not only on the product.

    Caught in production data: adding `bowl_count` re-derived every tap (their category
    had just gained a class, so their hash moved) and silently skipped all 1,148 kitchen
    sinks, whose inputs were untouched. They kept their old values and the run reported
    success, because "skipped" is also what a correct no-op looks like.
    """
    import app.services.product_spec_derivation as derivation

    _product(db, "ZZT-VER", "CABANA KITCHEN SINK (DOUBLE BOWL)")
    derive_for_code(db, "ZZT-VER")
    first = derive_for_code(db, "ZZT-VER")
    assert first["skipped"] and not first["written"], "same rules + same product = no work"

    monkeypatch.setattr(derivation, "DERIVATION_VERSION", "test-bump")
    after = derive_for_code(db, "ZZT-VER")
    assert after["written"] and not after["skipped"], "a rule change must re-derive"


# --------------------------------------------------------------------------- #
# the second real user report: WC flush type, trap length, basin overflow/screw
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "description,expected",
    [
        ("SORENTO ONE PIECE (SIPHONIC) WASH DOWN WC (S-TRAP:300MM)", "siphonic"),
        ("SORENTO ONE PIECE TWISTER FLUSH WC (S-TRAP 300MM)", "twister"),
        ("SORENTO ONE PIECE TWISTER  FLUSHING  WC (S-TRAP:250MM)", "twister"),
        ("CABANA CLOSE COUPLED WC - CISTERN WASH-DOWN FLUSHING", "washdown"),
        ("SORENTO ONE PIECE WASH DOWN WC (P-TRAP 180MM)", "washdown"),
    ],
)
def test_flush_type_is_read_from_the_description(db, description, expected):
    # flush_type is not class-gated in derivation itself (only advisory in the
    # registry's applies_when), so any category exercises the token match.
    _product(db, "ZZT-FLUSH", description)
    derive_for_code(db, "ZZT-FLUSH")
    assert _value(db, "ZZT-FLUSH", "flush_type") == expected


@pytest.mark.parametrize(
    "description,expected",
    [
        ("SORENTO ONE PIECE PEDESTAL TWISTER FLUSH WC (S-TRAP 300MM)", 300),
        ("SORENTO ONE PIECE TWISTER FLUSHING WC (S-TRAP:250MM)", 250),
        ("SORENTO ONE PIECE WASH DOWN WC (P-TRAP 180MM)", 180),
        ("SORENTO CERAMIC AUTO INDUCTION INTELLIGENT TOILET ( S- TRAP 250MM )", 250),
    ],
)
def test_trap_length_is_read_independently_of_trap_type(db, description, expected):
    _product(db, "ZZT-TLEN", description)
    derive_for_code(db, "ZZT-TLEN")
    assert _value(db, "ZZT-TLEN", "trap_length") == expected


@pytest.mark.parametrize(
    "description",
    [
        "SORENTO ONE PIECE TWISTER FLUSH WC (P-TRAP 180MM) SRTWC8354-SH-P (WITH UF SEAT COVER)",
        "SORENTO ONE PIECE WASH DOWN -  RIMLESS WC (S-TRAP:250MM) SRTWC289-RL",
        "SORENTO CERAMIC AUTO INDUCTION INTELLIGENT TOILET ( S- TRAP 250MM )",
    ],
)
def test_a_trap_length_is_never_read_as_the_length(db, description):
    """889 catalog rows state a trap length and no size; 843 spec rows had it as Length."""
    _product(db, "ZZT-TRAPL", description)
    derive_for_code(db, "ZZT-TRAPL")
    assert _value(db, "ZZT-TRAPL", "dim_length") is None
    assert _value(db, "ZZT-TRAPL", "trap_length") in (180, 250)


def test_a_lone_size_is_still_the_length_when_it_is_not_a_trap(db):
    _product(db, "ZZT-LONE", "SORENTO MARBLE TOP BASIN (800MM)")
    derive_for_code(db, "ZZT-LONE")
    assert _value(db, "ZZT-LONE", "dim_length") == 800


def test_overflow_is_read_whether_the_word_is_split_or_joined(db):
    """"OVER FLOW" (5 catalog rows) and "OVERFLOW" (137) must set the same key."""
    _product(db, "ZZT-OF1", "SORENTO UNDER COUNTER BASIN (560X375X175MM) C/W RECTANGULAR SHAPE OVER FLOW")
    derive_for_code(db, "ZZT-OF1")
    assert _value(db, "ZZT-OF1", "has_overflow") is True

    _product(db, "ZZT-OF2", "SORENTO WASH BASIN C/W OVERFLOW")
    derive_for_code(db, "ZZT-OF2")
    assert _value(db, "ZZT-OF2", "has_overflow") is True




@pytest.mark.parametrize(
    "description",
    [
        "SORENTO CERAMIC AUTO INDUCTION INTELLIGENT TOILET (300MM)",
        "SORENTO CERAMIC AUTO INDUCTION INTELLIGENT TOILET SRTWC018AF",
    ],
)
def test_intelligent_toilets_are_flagged_smart(db, description):
    _product(db, "ZZT-SMART", description)
    derive_for_code(db, "ZZT-SMART")
    assert _value(db, "ZZT-SMART", "is_smart") is True


def test_auto_induction_alone_is_still_smart(db):
    # 6 catalog rows say AUTO INDUCTION without the word INTELLIGENT.
    _product(db, "ZZT-AUTOI", "SORENTO CERAMIC AUTO INDUCTION TOILET SRTWC999")
    derive_for_code(db, "ZZT-AUTOI")
    assert _value(db, "ZZT-AUTOI", "is_smart") is True


def test_an_ordinary_wc_is_not_flagged_smart(db):
    _product(db, "ZZT-PLAIN", "SORENTO ONE PIECE WASH DOWN WC (P-TRAP 180MM)")
    derive_for_code(db, "ZZT-PLAIN")
    assert _value(db, "ZZT-PLAIN", "is_smart") is None


# --------------------------------------------------------------------------- #
# configurable rules + the flyer as a second source (#102)
# --------------------------------------------------------------------------- #
def test_a_configured_rule_derives_a_value_the_shipped_tables_never_had(db):
    """The point of the whole exercise: a new spec without a deploy."""
    _product(db, "ZZT-RULE-1", "SORENTO KITCHEN SINK WITH NANO COATING", brand="brand")

    derive_for_code(
        db,
        "ZZT-RULE-1",
        rules_by_key={"material": [{"match": "contains", "pattern": "NANO COATING", "value": "nano"}]},
    )

    assert _value(db, "ZZT-RULE-1", "material") == "nano"


def test_rule_order_is_priority(db):
    # "STAINLESS STEEL" must beat "STEEL", or every stainless product reads as steel.
    _product(db, "ZZT-RULE-2", "SORENTO STAINLESS STEEL SINK", brand="brand")

    derive_for_code(
        db,
        "ZZT-RULE-2",
        rules_by_key={
            "material": [
                {"match": "contains", "pattern": "STAINLESS STEEL", "value": "stainless_steel"},
                {"match": "contains", "pattern": "STEEL", "value": "steel"},
            ]
        },
    )

    assert _value(db, "ZZT-RULE-2", "material") == "stainless_steel"


def test_a_contains_rule_matches_whole_words_only(db):
    """`SQ` -> square must not fire on SQUATTING PAN.

    A plain substring search changed 42 of 11,415 live codes when the rule engine was
    first written, some into nonsense. Bounded matching is the shipped behaviour and
    moving rules into a table must not quietly loosen it.
    """
    _product(db, "ZZT-RULE-3", "SORENTO SQUATTING PAN ZZT-RULE-3", brand="brand")

    derive_for_code(
        db, "ZZT-RULE-3", rules_by_key={"shape": [{"match": "contains", "pattern": "SQ", "value": "square"}]}
    )

    assert _value(db, "ZZT-RULE-3", "shape") is None


# test_the_flyer_fills_a_gap_the_description_left (:861) is lifted onto
# `propose_from_text` in tests/test_product_spec_propose_from_text.py - it tests the
# pass itself, which survives the lift unchanged.
#
# test_the_description_beats_the_flyer (:881) is removed rather than lifted: it
# pinned the flyer LOSING to the description inside one `derive_for_code` call, and
# `derive_for_code` no longer takes flyer text as an input at all, so there is no
# longer a contest between the two to test here. See the note above
# test_the_code_suffix_still_answers_when_no_text_does for the rest of this cut.


def test_editing_a_rule_re_derives_rather_than_reporting_skipped(db):
    """The rules are half the input, so the hash has to include them.

    Without this an edit in the UI reports a successful run that changed nothing - the
    same "skipped" it reports when there is genuinely nothing to do.
    """
    _product(db, "ZZT-RULE-4", "SORENTO KITCHEN SINK WITH NANO COATING", brand="brand")
    derive_for_code(db, "ZZT-RULE-4", rules_by_key={})
    assert _value(db, "ZZT-RULE-4", "material") is None

    result = derive_for_code(
        db,
        "ZZT-RULE-4",
        rules_by_key={"material": [{"match": "contains", "pattern": "NANO COATING", "value": "nano"}]},
    )

    assert result["skipped"] == 0, "a changed rule must not look like nothing changed"
    assert _value(db, "ZZT-RULE-4", "material") == "nano"


def test_a_broken_rule_does_not_stop_the_catalog_deriving(db):
    # Rules are typed by hand. One bad regex must cost that rule, not the run.
    _product(db, "ZZT-RULE-5", "SORENTO S/STEEL KITCHEN SINK", brand="brand")

    derive_for_code(
        db,
        "ZZT-RULE-5",
        rules_by_key={
            "material": [
                {"match": "regex", "pattern": "([unclosed", "capture": 1},
                {"match": "contains", "pattern": "S/STEEL", "value": "stainless_steel"},
            ]
        },
    )

    assert _value(db, "ZZT-RULE-5", "material") == "stainless_steel"


# --------------------------------------------------------------------------- #
# source precedence: description, then flyer, then the code (#108)
#
# PR 4 (AC-B.18, captain amendment 2026-08-14): the flyer text pass is LIFTED out of
# derivation into a pure `propose_from_text(text, code)` in
# tests/test_product_spec_propose_from_text.py, not deleted. `derive_for_code` no
# longer takes a `flyer_text` argument at all, so every test below that pitted the
# flyer against the description INSIDE ONE DERIVATION CALL tested an ordering that no
# longer exists here - `propose_from_text` never sees a description, so "the flyer
# loses to the description" has no analogue to lift. Removed:
# - test_a_lower_rule_on_the_flyer_never_beats_a_higher_rule_on_the_description (:951)
# - test_a_size_in_the_description_is_not_overwritten_by_the_flyer (:1007)
# and test_the_description_beats_the_flyer above (:881) for the same reason. The pass
# itself (flyer text -> material/finish/dimensions/seat_material) is pinned in
# tests/test_product_spec_propose_from_text.py instead.
#
# test_words_on_the_flyer_beat_a_letter_pair_in_the_code (:967),
# test_the_flyer_supplies_dimensions_the_description_never_states (:994) and
# test_the_seat_cover_material_is_read_from_the_flyer (:1019) are also removed from
# here for the same reason (they used the now-gone `_flyer()`/`flyer_text` seam) and
# are lifted onto `propose_from_text` verbatim in that file.
#
# test_the_seat_material_stays_off_products_that_have_no_seat (:1030) is removed too:
# it used the same `_flyer()` helper, and the scope-gate it pinned (a class-gated key
# dropped for the wrong class) is not something `propose_from_text` can reproduce on
# its own - it never sees the PRODUCT's real class, only whatever a rule reads out of
# the pasted text itself. That coverage now lives at the route level (AC-B.4, using
# the product's actual stored class) in tests/test_product_spec_extract_route.py, plus
# two `_apply_scope` pins on `propose_from_text` itself in
# tests/test_product_spec_propose_from_text.py.
# --------------------------------------------------------------------------- #
def test_the_code_suffix_still_answers_when_no_text_does(db):
    # The other half: demoting the code must not disable it.
    _product(db, "ZZT-SRC-3-GY", "SORENTO CERAMIC ART BASIN ONLY ZZT-SRC-3-GY")

    derive_for_code(db, "ZZT-SRC-3-GY")

    assert _value(db, "ZZT-SRC-3-GY", "finish") == "grey"
