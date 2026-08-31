"""Running the seed twice changes nothing (AC-L.9).

Written before the script. The claim under test is not "it inserts eight rows",
which any INSERT does; it is that the SECOND run is a no-op - no new template,
no new asset row, and above all no second copy of 28 files in the bucket. That
last one is not hypothetical: 1,356 orphaned objects were once found under
``dealer_kit_asset/`` because something uploaded on every run and nothing
matched what was already there.

Postgres only, on a blank scratch schema, with storage faked in-process so the
run never touches a live bucket.
"""
from __future__ import annotations

import pytest

from app.models.company import Company
from app.models.dealer_kit import Asset, TagTemplate
from app.models.resources import Attachment
from app.schemas.price_tag import TagTemplateDocModel

from scripts import seed_tag_templates
from scripts.tag_template_seed_docs import SEED_TEMPLATES

from tests._fake_storage import patch_storage
from tests._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"


def _company(db) -> Company:
    """The scratch schema seeds Sorento; a seed run needs a code to resolve."""
    company = db.query(Company).filter(Company.id == SORENTO).first()
    if company is None:
        company = Company(id=SORENTO, name="ZZT Sorento", code=unique_code("ZS")[:50])
        db.add(company)
        db.flush()
    return company


def _counts(db) -> tuple[int, int, int]:
    from app.models.base import company_scope

    with company_scope(db, None):
        return (
            db.query(Asset).count(),
            db.query(TagTemplate).count(),
            db.query(Attachment)
            .filter(Attachment.entity_type == "dealer_kit_asset")
            .count(),
        )


@pytest.fixture
def seeded(monkeypatch):
    with blank_session() as db:
        storage = patch_storage(monkeypatch)
        company = _company(db)
        # The script commits; inside the scratch-schema session that is a
        # SAVEPOINT release, so the schema is still dropped on the way out.
        yield db, company, storage


def test_the_first_run_creates_eight_templates_and_the_manifest(seeded):
    db, company, storage = seeded

    result = seed_tag_templates.run(db, company_code=company.code, dry_run=False)

    expected_assets = len(seed_tag_templates.load_manifest())
    assert len(result.templates_created) == 8
    assert len(result.assets_created) == expected_assets
    assert result.assets_existing == []

    assets, templates, attachments = _counts(db)
    assert templates == 8
    assert assets == expected_assets
    assert attachments == expected_assets
    # One object per asset plus its thumbnail. The thumbnail is a separate key,
    # which is how half the bucket litter got there the first time.
    assert len(storage.objects) >= expected_assets


def test_a_second_run_changes_nothing(seeded):
    db, company, storage = seeded

    seed_tag_templates.run(db, company_code=company.code, dry_run=False)
    before = _counts(db)
    objects_before = dict(storage.objects)

    result = seed_tag_templates.run(db, company_code=company.code, dry_run=False)

    assert result.templates_created == []
    assert result.assets_created == []
    assert len(result.templates_existing) == 8
    assert _counts(db) == before
    assert storage.objects == objects_before


def test_a_second_run_does_not_rewrite_an_edited_template(seeded):
    """Marketing's edits survive a redeploy.

    The seed plants a starting point; the moment somebody moves a layer the
    template is theirs. A seed that reimposed its own layout would discard that
    work silently, on a schedule nobody controls.
    """
    from app.models.base import company_scope

    db, company, storage = seeded
    seed_tag_templates.run(db, company_code=company.code, dry_run=False)

    with company_scope(db, frozenset({company.id})):
        template = db.query(TagTemplate).filter(TagTemplate.family == "wc").one()
        edited = dict(template.doc)
        edited["layers"] = edited["layers"][:3]
        template.doc = edited
        db.commit()

    seed_tag_templates.run(db, company_code=company.code, dry_run=False)

    with company_scope(db, frozenset({company.id})):
        template = db.query(TagTemplate).filter(TagTemplate.family == "wc").one()
        assert len(template.doc["layers"]) == 3


def test_a_dry_run_writes_nothing_and_uploads_nothing(seeded):
    db, company, storage = seeded

    result = seed_tag_templates.run(db, company_code=company.code, dry_run=True)

    assert len(result.templates_created) == 8
    assert _counts(db) == (0, 0, 0)
    assert storage.objects == {}


def test_every_seeded_document_is_valid_and_names_real_assets(seeded):
    """The ids in a saved document resolve to asset rows that exist.

    A badge layer whose ``assetId`` matches nothing is an empty box on the tag,
    and the seed would have reported success either way.
    """
    from app.models.base import company_scope

    db, company, _storage = seeded
    seed_tag_templates.run(db, company_code=company.code, dry_run=False)

    with company_scope(db, frozenset({company.id})):
        known = {asset.id for asset in db.query(Asset).all()}
        templates = db.query(TagTemplate).all()

        assert {t.family for t in templates} == {f for f, _l, _b in SEED_TEMPLATES}

        for template in templates:
            TagTemplateDocModel.model_validate(template.doc)
            assert template.print_size == {
                "width_mm": template.doc["width_mm"],
                "height_mm": template.doc["height_mm"],
            }
            for layer in template.doc["layers"]:
                props = layer["props"]
                if props["kind"] == "badge":
                    assert props["assetId"] in known, (template.name, layer["id"])
                if props["kind"] == "image" and (props.get("source") or {}).get(
                    "type"
                ) == "asset":
                    assert props["source"]["assetId"] in known


def test_the_seeded_assets_belong_to_the_named_company(seeded):
    """Company scope is the whole reason the script takes a company code.

    A script starts with the scope UNSET, under which an owned write is refused
    outright. Getting this wrong does not produce wrong data, it produces a
    seed that cannot run - so it is worth an assertion rather than a comment.
    """
    from app.models.base import company_scope

    db, company, _storage = seeded
    seed_tag_templates.run(db, company_code=company.code, dry_run=False)

    with company_scope(db, None):
        for asset in db.query(Asset).all():
            assert asset.company_id == company.id
        for template in db.query(TagTemplate).all():
            assert template.company_id == company.id


def test_an_unknown_company_code_stops_before_writing_anything(seeded):
    db, _company, storage = seeded

    with pytest.raises(SystemExit):
        seed_tag_templates.run(db, company_code="ZZT-NOPE", dry_run=False)

    assert _counts(db) == (0, 0, 0)
    assert storage.objects == {}


def test_reference_artwork_is_not_uploaded():
    """The price-badge and header-band samples are for a human to look at.

    Uploading them would leave marketing choosing between the badge layer and a
    picture of a badge, and the picture would win about half the time.
    """
    names = {entry["file"] for entry in seed_tag_templates.load_manifest()}
    assert not any(name.startswith("reference_") for name in names)
    assert "brand_header_band_sample.png" not in names
