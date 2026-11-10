"""QUOTE-COVER-FIELDS: the fax number on a party, a quotation document and the company settings.

Postgres only via ``blank_session``; the chain is seeded with the helpers of the quotation PDF
tests (CI's database is empty).
"""
from __future__ import annotations

from app.api.v1.user_management.settings import (
    SystemSettingUpdate,
    _update_general_settings_impl,
)
from app.models.user import SystemSetting

from ._pg_fixture import blank_session
from .test_project_quotation_pdf import _setup


def test_party_create_and_update_round_trip_fax():
    from app.services import project_reference_service as refs

    with blank_session() as db:
        env = _setup(db)
        party, created = refs.create_party(
            db,
            company_id=env["company_id"],
            payload={"party_type": "developer", "name": "zzt-fax Party", "fax": "03-1111 2222"},
            actor_user_id=env["owner"],
        )
        assert created and party.fax == "03-1111 2222"
        refs.update_party(db, party, {"fax": "03-9999 0000"})
        db.refresh(party)
        assert party.fax == "03-9999 0000"
        listed = {row["id"]: row for row in refs.serialize_parties(db, [party])}
        assert listed[party.id]["fax"] == "03-9999 0000"


def test_party_schemas_accept_and_expose_fax():
    from app.schemas.projects import ProjectPartyCreate, ProjectPartyResponse, ProjectPartyUpdate

    assert ProjectPartyCreate(party_type="developer", name="x", fax="1").fax == "1"
    assert ProjectPartyUpdate(fax="2").model_dump(exclude_unset=True) == {"fax": "2"}
    assert "fax" in ProjectPartyResponse.model_fields


def test_new_document_snapshots_party_fax_and_serializer_returns_it():
    from app.models.projects import ProjectParty
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        env = _setup(db, developer_address="zzt-fax Level 8", developer_phone="012-345 6789")
        party = db.query(ProjectParty).filter(ProjectParty.id == env["party"].id).one()
        party.fax = "03-5555 6666"
        db.flush()
        document = qdocs.create_document(db, project=env["project"], actor_user_id=env["owner"])
        assert document.recipient_fax_snapshot == "03-5555 6666"
        payload = qdocs.serialize_document(db, document)
        assert payload["recipient_fax_snapshot"] == "03-5555 6666"


def test_settings_general_update_round_trips_fax():
    with blank_session() as db:
        db.add(SystemSetting(id="ss-fax"))
        db.commit()
        _update_general_settings_impl(SystemSettingUpdate(fax="03-7777 8888"), db)
        row = db.query(SystemSetting).first()
        assert row.fax == "03-7777 8888"
