"""Security-review fix round (#1286): findings B1, S1, S2 and N1, one test each or more.

B1 - a Words phrase with several "..." gaps backtracked catastrophically (three segments,
8.8 s over 4.9k characters). Refused on save, and skipped at read time for a row stored
before the refusal existed, so it can never hang derivation.
S1 - the synchronous re-read on a rule save or a rule remove shares ONE guard with the
catalogue preview: while one runs, the next is refused with a 409 and nothing is saved.
S2 - brand binding and the understanding vocabulary read through the company scope, and
fail closed when no scope was ever set.
N1 - one brand name is never both offered and held back.
"""
from __future__ import annotations

import logging
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.base import company_scope
from app.models.company import Company
from app.models.product import Brand
from app.models.product_spec import ProductSpecRegistry
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session


def _uid() -> str:
    return str(uuid.uuid4())


def _refused(rules, **kwargs) -> AppException:
    from app.services.product_spec_rules import validate_rules

    with pytest.raises(AppException) as excinfo:
        validate_rules(rules, data_type="boolean", **kwargs)
    return excinfo.value


# --------------------------------------------------------------------------- #
# B1
# --------------------------------------------------------------------------- #
def test_sec_b1_a_phrase_with_two_gaps_is_refused():
    error = _refused([{"builder": {"kind": "words", "words": ["A ... B ... C"], "value": True}}])
    assert error.status_code == 400
    assert error.message == "Rule 1: use at most one ... in a phrase."


def test_sec_b1_the_gap_limit_covers_every_list_of_words():
    error = _refused(
        [{"builder": {"kind": "number", "before": ["MM"], "skip_after": ["A ... B ... C"]}}],
    )
    assert error.message == "Rule 1: use at most one ... in a phrase."


def test_sec_b1_more_than_twenty_words_in_a_rule_is_refused():
    words = [f"WORD{n}" for n in range(21)]
    error = _refused([{"builder": {"kind": "words", "words": words, "value": True}}])
    assert error.status_code == 400
    assert error.message == "Rule 1: use at most 20 words in a list."
    assert "_" not in error.message


def test_sec_b1_a_word_longer_than_sixty_characters_is_refused():
    error = _refused([{"builder": {"kind": "words", "words": ["X" * 61], "value": True}}])
    assert error.status_code == 400
    assert error.message == "Rule 1: keep each word to 60 characters or fewer."


def test_sec_b1_a_one_gap_phrase_over_a_long_text_with_no_full_stop_is_fast():
    from app.services.product_spec_rules import read_text

    builder = {"kind": "words", "words": ["PP ... SEAT"], "value": "pp"}
    haystack = ("PP COVER " * 600)[:5000]
    texts = {"description": haystack, "flyer": "", "class_tail": ""}

    started = time.perf_counter()
    assert read_text(builder, texts, "") is None
    assert time.perf_counter() - started < 0.5


def test_sec_b1_a_stored_two_gap_phrase_reads_nothing_and_warns(caplog):
    from app.services.product_spec_rules import read_text

    builder = {"kind": "words", "words": ["PP ... SOFT ... SEAT"], "value": "pp"}
    haystack = ("PP SOFT COVER " * 400)[:4900]
    texts = {"description": haystack, "flyer": "", "class_tail": ""}

    started = time.perf_counter()
    with caplog.at_level(logging.WARNING):
        assert read_text(builder, texts, "") is None
    assert time.perf_counter() - started < 0.5
    assert any("..." in record.getMessage() for record in caplog.records)


# --------------------------------------------------------------------------- #
# S1
# --------------------------------------------------------------------------- #
BUSY = "Products are still being updated from another change. Try again in a moment."


@pytest.fixture
def busy():
    """A catalogue read already running (a preview holds the one slot)."""
    from app.services import product_spec_preview

    with product_spec_preview._RUNNING_LOCK:
        assert product_spec_preview._RUNNING_JOB_ID is None
        product_spec_preview._RUNNING_JOB_ID = "zzt-running"
    try:
        yield
    finally:
        with product_spec_preview._RUNNING_LOCK:
            product_spec_preview._RUNNING_JOB_ID = None


@pytest.fixture
def api(monkeypatch):
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    with blank_session() as db:
        app.dependency_overrides[get_db] = lambda: db
        user = {"id": _uid(), "email": "sec@example.com"}
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_user_or_api_key] = lambda: user
        app.dependency_overrides[apply_company_scope] = lambda: None
        monkeypatch.setattr(
            UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
        )
        monkeypatch.setattr(
            UserPermissionService,
            "get_user_permission_slugs",
            lambda self, uid: {"master_data.spec_registry.edit", "master_data.spec_registry.view"},
        )
        try:
            yield TestClient(app), db
        finally:
            app.dependency_overrides.clear()


def _key(db) -> ProductSpecRegistry:
    row = ProductSpecRegistry(
        id=_uid(),
        spec_key=f"zzt_{_uid()[:8]}",
        label="ZZT",
        data_type="enum",
        allowed_values=["a"],
        synonyms={"a": ["a"]},
        source="user",
        derivation_rules=[{"builder": {"kind": "words", "words": ["OLD"], "value": "a"}}],
    )
    db.add(row)
    db.commit()
    return row


def test_sec_s1_a_rule_save_while_a_catalogue_read_runs_is_refused_and_not_stored(api, busy):
    client, db = api
    row = _key(db)

    response = client.patch(
        f"/api/v1/master-data/spec-registry/{row.spec_key}",
        json={"derivation_rules": [{"builder": {"kind": "words", "words": ["NEW"], "value": "a"}}]},
    )

    assert response.status_code == 409, response.text
    assert response.json()["message"] == BUSY
    db.expire_all()
    stored = db.query(ProductSpecRegistry).filter_by(spec_key=row.spec_key).one()
    assert stored.derivation_rules == [{"builder": {"kind": "words", "words": ["OLD"], "value": "a"}}]


def test_sec_s1_a_label_save_is_not_held_up_by_a_catalogue_read(api, busy):
    client, db = api
    row = _key(db)

    response = client.patch(
        f"/api/v1/master-data/spec-registry/{row.spec_key}", json={"label": "Renamed"}
    )

    assert response.status_code == 200, response.text


def test_sec_s1_a_rule_remove_while_a_catalogue_read_runs_fails_and_keeps_the_rule(
    api, busy, monkeypatch
):
    from app.services import product_spec_registry
    from app.services.product_spec_registry import remove_rule

    _client, db = api
    row = _key(db)
    # A remove waits for the other read (review S-8); this one outlasts the wait.
    monkeypatch.setattr(product_spec_registry, "REMOVE_WAIT_SECONDS", 0.3)

    with pytest.raises(AppException) as excinfo:
        remove_rule(db, row.spec_key, {"kind": "words", "words": ["OLD"], "value": "a"})

    assert excinfo.value.status_code == 409
    assert excinfo.value.message == BUSY
    db.expire_all()
    assert db.query(ProductSpecRegistry).filter_by(spec_key=row.spec_key).one().derivation_rules


def test_sec_s1_the_slot_is_given_back_after_a_save(api):
    from app.services import product_spec_preview

    client, db = api
    row = _key(db)

    response = client.patch(
        f"/api/v1/master-data/spec-registry/{row.spec_key}",
        json={"derivation_rules": [{"builder": {"kind": "words", "words": ["NEW"], "value": "a"}}]},
    )

    assert response.status_code == 200, response.text
    assert product_spec_preview._RUNNING_JOB_ID is None


# --------------------------------------------------------------------------- #
# S2 and N1
# --------------------------------------------------------------------------- #
@pytest.fixture
def two_companies():
    from app.services.product_spec_registry import seed_spec_registry

    with blank_session() as db:
        with company_scope(db, None):
            second = Company(id=_uid(), name="ZZT Second Co", code=f"Z{_uid()[:5]}")
            db.add(second)
            db.flush()
            house = Brand(id=_uid(), brand_code="ZZT-SRT", brand_name="SORENTO")
            others = Brand(id=_uid(), brand_code="ZZT-OTH", brand_name="OTHERS", is_searchable=False)
            db.add_all([house, others])
            db.flush()
            rival = Brand(id=_uid(), brand_code="ZZT-BRV", brand_name="BRAVAT", company_id=second.id)
            hidden = Brand(
                id=_uid(),
                brand_code="ZZT-NLG",
                brand_name="NO LOGO",
                company_id=second.id,
                is_searchable=False,
            )
            db.add_all([rival, hidden])
            db.flush()
            seed_spec_registry(db)
        db.info["refs"] = {"second": second.id, "first": house.company_id}
        yield db


def test_sec_s2_a_company_scope_binds_only_that_companys_brand(two_companies):
    from app.services.product_spec_search import resolve_terms_to_specs

    db = two_companies
    with company_scope(db, frozenset({db.info["refs"]["second"]})):
        resolved = resolve_terms_to_specs(db, ["bravat", "sorento", "kitchen", "sink"])
        assert {"key": "brand", "value": "BRAVAT"} in resolved
        assert {"key": "brand", "value": "SORENTO"} not in resolved
        # That company's own placeholder: held back as a single word, bound in full.
        assert {"key": "brand", "value": "NO LOGO"} in resolve_terms_to_specs(db, ["no", "logo", "sink"])


def test_sec_s2_a_company_scope_offers_only_that_companys_names(two_companies):
    from app.services.product_spec_understanding import _vocabulary

    db = two_companies
    with company_scope(db, frozenset({db.info["refs"]["second"]})):
        described, _index, _open = _vocabulary(db)
    brand = next(entry for entry in described if entry["spec_key"] == "brand")
    assert brand["allowed_values"] == ["BRAVAT"]


def test_sec_s2_an_unset_scope_binds_no_brand_and_offers_none(two_companies):
    from app.services.product_spec_search import resolve_terms_to_specs
    from app.services.product_spec_understanding import _vocabulary

    db = two_companies
    db.info.pop("company_scope", None)
    resolved = resolve_terms_to_specs(db, ["bravat", "sorento", "sink"])
    assert not any(entry["key"] == "brand" for entry in resolved)
    described, _index, _open = _vocabulary(db)
    assert not any(entry["spec_key"] == "brand" for entry in described)


def test_sec_n1_a_name_offered_in_one_company_is_never_also_held_back(two_companies):
    from app.services.product_spec_search import unsearchable_brand_names
    from app.services.product_spec_understanding import _brand_vocabulary

    db = two_companies
    with company_scope(db, None):
        # The second company marks NO LOGO a placeholder; the first calls a real brand
        # NO LOGO. Across all companies it is offered, so it is not held back. (OTHERS
        # is never offered at all, whatever a row says: review S-2.)
        db.add(Brand(id=_uid(), brand_code="ZZT-NLG1", brand_name="NO LOGO"))
        db.flush()
        vocabulary = _brand_vocabulary(db)
        held_back = unsearchable_brand_names(db)

    assert "NO LOGO" in vocabulary.allowed_values
    assert "NO LOGO" not in vocabulary.excluded_values
    assert "no logo" not in held_back
    assert "others" in held_back
