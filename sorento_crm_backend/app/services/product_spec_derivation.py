"""Read specs out of the catalog. Deterministically, or not at all.

There is no inference in this module and that is deliberate. Two mechanisms that
needed it were measured and rejected: curating specs out of the description (bowl count
appears in 110 of 22,366 descriptions), and inducing dimensions from code conventions
(best rule 25.3% against 387 labelled rows, where 99% was required). What is left is
what can be read directly, so every value here is defensible by pointing at the
substring it came from.

Precedence, highest first:

  1. a `source='human'` value already stored   - a reviewer settled it, never touch it
  2. the products table's own columns          - curated data outranks parsed text
  3. literal tokens in the description         - shape-gated, see below
  4. a closed code lookup (the finish suffix)
  5. nothing

Rule 5 is not a failure mode. A NULL spec leaves the row to the other ranking legs,
where a guessed one would actively boost a wrong candidate.

SHAPE GATING is the subtle part. `products` has only length/width/height, so a round
basin's diameter has been forced into `length` across the catalog:

    CONCRETE ROUND BASIN (407X120X10MM)  ->  length=407 width=120 height=10
                                              ^ diameter ^ depth  ^ thickness

For a round or square product the stored columns are therefore mis-keyed, not merely
different, so they are NOT trusted for length/width and the row is flagged for a human.
231 codes catalog-wide have length = width, which is the same defect showing up without
the description saying so.

Ticket: jayson-odoo/sorento-crm#74.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.product import Product, ProductCategory
from app.models.product_spec import ProductSpecException, ProductSpecifications
from app.services.product_spec_rendering import render_spec_sentence

# --------------------------------------------------------------------------- #
# vocabulary, mirroring the Spec Registry's allowed_values
# --------------------------------------------------------------------------- #

# Longest first: "STAINLESS STEEL" must win before "STEEL" matches.
MATERIAL_TOKENS: list[tuple[str, str]] = [
    ("STAINLESS STEEL", "stainless_steel"),
    ("S/STEEL", "stainless_steel"),
    ("STAINLESS", "stainless_steel"),
    ("TEMPERED GLASS", "glass"),
    ("CERAMIC", "ceramic"),
    ("PORCELAIN", "ceramic"),
    ("ACRYLIC", "acrylic"),
    ("GLASS", "glass"),
    ("BRASS", "brass"),
    ("PVC", "pvc"),
]

MOUNTING_TOKENS: list[tuple[str, str]] = [
    ("WALL HUNG", "wall_hung"),
    ("WALL MOUNTED", "wall_hung"),
    ("WALL MOUNT", "wall_hung"),
    ("FLOOR STANDING", "floor_standing"),
    ("FLOOR MOUNTED", "floor_standing"),
    ("FREE STANDING", "floor_standing"),
    ("COUNTER TOP", "counter_top"),
    ("COUNTERTOP", "counter_top"),
    ("ABOVE COUNTER", "counter_top"),
    ("CONCEALED", "concealed"),
    ("PEDESTAL", "pedestal"),
]

CONTROL_TOKENS: list[tuple[str, str]] = [
    ("SINGLE LEVER", "single_lever"),
    ("SINGLE HANDLE", "single_lever"),
    ("PILLAR", "pillar"),
    ("MIXER", "mixer"),
    ("BIB", "bib"),
]

SHAPE_TOKENS: list[tuple[str, str]] = [
    ("RECTANGULAR", "rectangular"),
    ("ROUND", "round"),
    ("SQUARE", "square"),
    ("OVAL", "oval"),
    ("ELLIPSE", "oval"),
    ("SQ", "square"),
]

# Trailing code segment -> finish. Everything absent here yields nothing: DIY is
# packaging, ENG is the -P-ENG collision family, bare digits are variant numbering.
FINISH_SUFFIXES: dict[str, str] = {
    "BL": "black",
    "GM": "gunmetal",
    "NL": "nickel",
    "GY": "grey",
    "RG": "rose_gold",
    "CR": "chrome",
    "FRG": "french_gold",
    "WH": "white",
    "SC": "satin_chrome",
}

# Nouns that mean "a part of a product", not a product. Matched as the HEAD of the
# phrase, never as a feature: a sink with a drainer board is still a sink.
#
#   "S/STEEL KITCHEN SINK DRAINER (440x200x100MM)"     -> accessory, DRAINER is the head
#   "CABANA KITCHEN SINK (...) CKS1050 -1 BOWL 1 DRAINER-" -> a SINK that has a drainer
#
# Real catalog data caught this: 22 kitchen sinks were flagged as accessories on the
# word DRAINER alone, which would have heavily deboosted genuine products in the very
# ranking case the accessory rule exists to protect.
ACCESSORY_NOUNS = (
    "WASTE",
    "BASKET",
    "DRAINER",
    "TAIL PIPE",
    "DRAIN PIPE",
    "BRACKET",
    "AIR PUMP",
    "SPARE",
    "HOSE",
    "HOLDER",
    "COVER",
)
ACCESSORY_CATEGORY_CODES = {"SRTPART", "MISC"}

# No sanitaryware product is five metres in any direction. Real catalog data carries
# separator typos ("540X440180MM" parses as 540 x 440180), and a dimension that absurd
# would otherwise be indexed and ranked on. Out-of-range values are dropped and flagged
# rather than silently stored.
MAX_PLAUSIBLE_MM = 5000

# 2 to 4 numbers separated by x / X / *, with optional spaces and an optional unit.
_DIM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[xX*]\s*(\d+(?:\.\d+)?)"
    r"(?:\s*[xX*]\s*(\d+(?:\.\d+)?))?"
    r"(?:\s*[xX*]\s*(\d+(?:\.\d+)?))?",
)


def _find_token(haystack: str, table: list[tuple[str, str]]) -> tuple[str, str] | None:
    """First (value, evidence) whose token appears literally. Order is precedence."""
    for token, value in table:
        if re.search(rf"(?<![A-Z]){re.escape(token)}(?![A-Z])", haystack):
            return value, token
    return None


def _accessory_noun_evidence(description: str) -> str | None:
    """The accessory noun heading this phrase, or None when it is only a feature.

    A noun reads as a FEATURE (so the product is not an accessory) when it follows a
    quantity or a "with": "1 DRAINER", "C/W BASKET", "WITH WASTE". Otherwise the noun
    heads the phrase and the product really is a part: "KITCHEN SINK DRAINER".
    """
    for noun in ACCESSORY_NOUNS:
        for match in re.finditer(rf"(?<![A-Z]){re.escape(noun)}(?![A-Z])", description):
            preceding = description[max(0, match.start() - 14) : match.start()]
            if re.search(r"(\d\s*$)|((?:C\s*/\s*W|WITH|AND)\s*$)", preceding):
                continue  # a feature of the product, not the product itself
            return noun
    return None


def _number(raw: str) -> float | int:
    value = float(raw)
    return int(value) if value.is_integer() else value


def _dimensions(description: str) -> tuple[list[float | int], str] | None:
    match = _DIM_RE.search(description or "")
    if not match:
        return None
    numbers = [_number(g) for g in match.groups() if g is not None]
    if len(numbers) < 2:
        return None
    return numbers, match.group(0)


class _Derivation:
    """Accumulates values, provenance and exceptions for one product code."""

    def __init__(self) -> None:
        self.values: dict[str, dict] = {}
        self.provenance: dict[str, dict] = {}
        self.exceptions: list[dict] = []

    def set(self, key: str, value, evidence: str, *, unit: str | None = None, source: str = "derived") -> None:
        if value is None:
            return
        entry: dict = {"value": value}
        if unit:
            entry["unit"] = unit
        self.values[key] = entry
        self.provenance[key] = {"source": source, "confidence": 1.0, "evidence": evidence}

    def flag(self, spec_key: str, reason: str, proposed=None, stored=None) -> None:
        self.exceptions.append(
            {"spec_key": spec_key, "reason": reason, "proposed": proposed, "stored": stored}
        )


def derive(product: Product, category: ProductCategory | None) -> _Derivation:
    """Everything readable about one product. Pure: no session, no writes."""
    out = _Derivation()
    description = (product.description or "").upper()
    code = (product.product_code or "").upper()

    # 1. class and brand, straight off the category
    if category is not None and category.class_label:
        out.set("class", category.class_label, category.category_code)
        if category.brand_hint:
            out.set("brand", category.brand_hint, category.category_code)

    # 2. accessory discriminator
    accessory_evidence = None
    if code.startswith("ACC-"):
        accessory_evidence = "ACC-"
    elif category is not None and (category.category_code or "").upper() in ACCESSORY_CATEGORY_CODES:
        accessory_evidence = category.category_code
    elif re.search(r"\bONLY\b", description):
        accessory_evidence = "ONLY"
    else:
        accessory_evidence = _accessory_noun_evidence(description)
    out.set("is_accessory", accessory_evidence is not None, accessory_evidence or code)

    # 3. shape. Never defaulted: "unstated" and "rectangular" are different, and the
    #    dimension rules below turn on which one it is.
    shape = None
    found = _find_token(description, SHAPE_TOKENS)
    if found:
        shape, evidence = found
        out.set("shape", shape, evidence)

    # 4. dimensions, gated on shape
    parsed = _dimensions(description)
    stored = {
        "dim_length": product.dimensions_length,
        "dim_width": product.dimensions_width,
        "dim_height": product.dimensions_height,
    }
    has_stored = any(v is not None for v in stored.values())

    if shape in ("round", "square"):
        # The stored columns are mis-keyed for these: 407 is a diameter, not a length.
        if parsed:
            numbers, evidence = parsed
            out.set("diameter", numbers[0], evidence, unit="mm")
            if len(numbers) > 1:
                out.set("depth", numbers[1], evidence, unit="mm")
            if len(numbers) > 2:
                out.set("thickness", numbers[2], evidence, unit="mm")
        if has_stored:
            out.flag(
                "diameter",
                "shape_mismatch",
                proposed={"shape": shape},
                stored={k: float(v) for k, v in stored.items() if v is not None},
            )
    else:
        described: dict[str, float | int] = {}
        evidence = ""
        if parsed:
            numbers, evidence = parsed
            for key, number in zip(("dim_length", "dim_width", "dim_height"), numbers):
                if number > MAX_PLAUSIBLE_MM:
                    out.flag(key, "implausible_dimension", proposed={"value": number, "evidence": evidence})
                    continue
                described[key] = number
            if len(numbers) > 3:
                out.set("thickness", numbers[3], evidence, unit="mm")

        for key, column_value in stored.items():
            if column_value is not None:
                # Curated data outranks parsed text.
                out.set(key, _number(str(column_value)), f"{key}={column_value}", unit="mm")
                if key in described and described[key] != _number(str(column_value)):
                    out.flag(
                        key,
                        "column_conflict",
                        proposed={"value": described[key], "evidence": evidence},
                        stored={"value": float(column_value)},
                    )
            elif key in described:
                out.set(key, described[key], evidence, unit="mm")

        # length == width is the fingerprint of a round or square product forced into
        # rectangular columns, even when the description never says so.
        length, width = stored["dim_length"], stored["dim_width"]
        if length is not None and width is not None and length == width:
            out.flag(
                "shape",
                "shape_mismatch",
                proposed={"shape": "round_or_square"},
                stored={"dim_length": float(length), "dim_width": float(width)},
            )

    # 5. description vocabulary
    for key, table in (
        ("material", MATERIAL_TOKENS),
        ("mounting", MOUNTING_TOKENS),
        ("control_type", CONTROL_TOKENS),
    ):
        hit = _find_token(description, table)
        if hit:
            value, evidence = hit
            out.set(key, value, evidence)

    # 6. finish, from the trailing code segment
    if "-" in code:
        suffix = code.rsplit("-", 1)[1]
        finish = FINISH_SUFFIXES.get(suffix)
        if finish:
            out.set("finish", finish, f"-{suffix}")

    return out


def _input_hash(product: Product, category: ProductCategory | None) -> str:
    parts = [
        product.product_code or "",
        product.description or "",
        (category.category_code if category else "") or "",
        (category.class_label if category else "") or "",
        str(product.dimensions_length),
        str(product.dimensions_width),
        str(product.dimensions_height),
    ]
    return hashlib.sha256("||".join(parts).encode()).hexdigest()


def derive_for_code(db: Session, product_code: str, *, commit: bool = False) -> dict:
    """Derive one code and fan the result out to every row that shares it.

    COMPANY SCOPE MATTERS HERE. A product code exists once per company, so the fan-out
    only reaches every copy when the session scope is all-companies (``None``). This
    function deliberately does NOT force that: a request-time re-derive must stay
    inside its caller's isolation. The catalog-wide batch job is the thing that runs
    unscoped, and `derive_all` documents it.
    """
    rows = (
        db.query(Product, ProductCategory)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .filter(Product.product_code == product_code)
        .order_by(Product.company_id, Product.id)
        .all()
    )
    if not rows:
        return {"written": 0, "skipped": 0, "exceptions": 0}

    # One derivation is written to every copy, so WHICH copy it reads from matters.
    # The company copies of a model can sit in different categories, and only some of
    # those categories are classified. Taking whichever row the database happened to
    # return first silently dropped class and brand for 40 of 594 pilot codes, and
    # made the result depend on row order. Prefer a classified category, then fall
    # back, and order the query so the fallback is at least deterministic.
    product, category = next(
        (pair for pair in rows if pair[1] is not None and pair[1].class_label),
        rows[0],
    )
    fingerprint = _input_hash(product, category)

    existing = {
        spec.product_id: spec
        for spec in db.query(ProductSpecifications)
        .filter(ProductSpecifications.product_id.in_([p.id for p, _ in rows]))
        .all()
    }

    if existing and len(existing) == len(rows) and all(
        spec.derived_hash == fingerprint for spec in existing.values()
    ):
        return {"written": 0, "skipped": len(rows), "exceptions": 0}

    result = derive(product, category)

    written = 0
    for row_product, _ in rows:
        spec = existing.get(row_product.id)
        if spec is None:
            spec = ProductSpecifications(product_id=row_product.id)
            db.add(spec)

        # A reviewer-confirmed value outranks anything derivable.
        kept_values, kept_provenance = {}, {}
        for key, entry in (spec.provenance or {}).items():
            if entry.get("source") == "human":
                kept_provenance[key] = entry
                if key in (spec.values or {}):
                    kept_values[key] = spec.values[key]

        spec.values = {**result.values, **kept_values}
        spec.provenance = {**result.provenance, **kept_provenance}
        # The only text spec search may match. Rendered here so it can never drift
        # from the values it describes.
        spec.rendered_text = render_spec_sentence(spec.values)
        spec.derived_hash = fingerprint
        spec.status = "needs_review" if result.exceptions else "derived"
        written += 1

    # Rebuild this code's open exceptions rather than appending, so a fixed input
    # clears its flag instead of accumulating a duplicate every run.
    db.query(ProductSpecException).filter(
        ProductSpecException.product_code == product_code,
        ProductSpecException.resolved_at.is_(None),
    ).delete(synchronize_session=False)
    for flagged in result.exceptions:
        db.add(
            ProductSpecException(
                id=str(uuid.uuid4()),
                product_code=product_code,
                spec_key=flagged["spec_key"],
                reason=flagged["reason"],
                proposed=flagged["proposed"],
                stored=flagged["stored"],
            )
        )

    db.flush()
    if commit:
        db.commit()

    return {"written": written, "skipped": 0, "exceptions": len(result.exceptions)}


def derive_all(
    db: Session,
    *,
    codes: list[str] | None = None,
    chunk_size: int = 500,
    commit: bool = False,
) -> dict:
    """Derive a batch of codes. Resumable by passing the codes still outstanding.

    Run this with the all-companies scope (``company_scope(db, None)``) so one
    derivation lands on every copy of a model. Under a single-company scope it will
    quietly cover half the catalog and the two copies will drift, which is the exact
    failure the code-keyed fan-out exists to prevent.
    """
    if codes is None:
        codes = [c for (c,) in db.query(Product.product_code).distinct().all()]

    totals = {"codes": 0, "written": 0, "skipped": 0, "exceptions": 0}
    for index in range(0, len(codes), chunk_size):
        for code in codes[index : index + chunk_size]:
            result = derive_for_code(db, code)
            totals["codes"] += 1
            for key in ("written", "skipped", "exceptions"):
                totals[key] += result[key]
        if commit:
            db.commit()

    return totals
