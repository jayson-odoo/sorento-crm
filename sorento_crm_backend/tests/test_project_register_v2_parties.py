"""PROJECT-REGISTER-V2 UAC B1, B3, B4 (party search and create on the spot)."""
from __future__ import annotations

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_register_v2_support import as_user, developer, uid, v2  # noqa: F401

PARTIES = "/api/v1/project-sales/parties/"


def _count(w, party_type: str, name: str) -> int:
    from sqlalchemy import func

    from app.models.projects import ProjectParty

    w.db.expire_all()
    return (
        w.db.query(ProjectParty)
        .filter(
            ProjectParty.company_id == w.company_id,
            ProjectParty.party_type == party_type,
            func.lower(ProjectParty.name) == name.lower(),
        )
        .count()
    )


def test_b1_search_finds_an_architect_that_sorts_after_the_200th(v2):
    from app.models.projects import ProjectParty

    v2.db.add_all(
        ProjectParty(
            id=uid(), company_id=v2.company_id, party_type="architect",
            name=f"CONTOH Architect {n:03d}",
        )
        for n in range(205)
    )
    developer(v2.db, v2.company_id, "CONTOH Architect 204")  # same name, other type
    v2.db.flush()
    res = as_user(v2, v2.owner).get(
        PARTIES, params={"party_type": "architect", "query": "Architect 204", "limit": 20}
    )
    assert res.status_code == 200, res.text
    rows = res.json()["data"]
    assert [r["name"] for r in rows] == ["CONTOH Architect 204"]
    assert rows[0]["party_type"] == "architect"


def test_b3_creating_a_party_without_parties_edit_is_403(v2):
    res = as_user(v2, v2.sales_b).post(PARTIES, json={"name": "CONTOH Nope", "party_type": "architect"})
    assert res.status_code == 403, res.text
    assert _count(v2, "architect", "CONTOH Nope") == 0


def test_b2_a_holder_of_parties_edit_creates_with_name_and_type_only(v2):
    res = as_user(v2, v2.owner).post(PARTIES, json={"name": "CONTOH New Builder", "party_type": "main_contractor"})
    assert res.status_code == 201, res.text
    assert res.json()["name"] == "CONTOH New Builder"


def test_b4_the_same_name_in_other_case_and_spacing_returns_the_existing_party(v2):
    first = as_user(v2, v2.owner).post(PARTIES, json={"name": "CONTOH Dev Sdn Bhd", "party_type": "developer"})
    assert first.status_code == 201, first.text
    again = as_user(v2, v2.owner).post(
        PARTIES, json={"name": "  contoh   DEV sdn  bhd ", "party_type": "developer"}
    )
    assert again.status_code == 200, again.text
    assert again.json()["id"] == first.json()["id"]
    assert _count(v2, "developer", "CONTOH Dev Sdn Bhd") == 1


def test_b4_the_same_name_for_another_type_is_a_new_party(v2):
    first = as_user(v2, v2.owner).post(PARTIES, json={"name": "CONTOH Shared Name", "party_type": "developer"})
    other = as_user(v2, v2.owner).post(PARTIES, json={"name": "CONTOH Shared Name", "party_type": "architect"})
    assert other.status_code == 201, other.text
    assert other.json()["id"] != first.json()["id"]


def test_b4_an_inactive_party_of_the_same_name_is_not_reused(v2):
    from app.models.projects import ProjectParty

    old = ProjectParty(
        id=uid(), company_id=v2.company_id, party_type="developer",
        name="CONTOH Retired Dev", is_active=False,
    )
    v2.db.add(old)
    v2.db.flush()
    res = as_user(v2, v2.owner).post(PARTIES, json={"name": "contoh retired dev", "party_type": "developer"})
    assert res.status_code == 201, res.text
    assert res.json()["id"] != old.id
