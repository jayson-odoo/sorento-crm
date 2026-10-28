"""PROJECT-REGISTER-V2 UAC C2-C6, C9: POST /api/v1/project-sales/projects/ai-extract.

No real provider is ever called: `AIExtractService.extract` is stubbed (or `_resolve_provider`
returns a provider that raises, for C6). Response shape bound here: top-level keys developer,
architect, main_contractor, project_type, state, mukim, customer, title, each a proposal whose
`status` is match | new | not_found (a wrapper key `proposals` is tolerated).
"""
from __future__ import annotations

import json

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_register_v2_support import (  # noqa: F401
    AI_EXTRACT,
    as_user,
    developer,
    project_type,
    uid,
    v2,
)

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)
FORM_KEY = "portal.project_registration"


@pytest.fixture
def clean_keys(v2):
    yield
    from app.services.queue_service import redis_conn

    try:
        for key in redis_conn.scan_iter(f"*{v2.owner}*"):
            redis_conn.delete(key)
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture
def extracted(monkeypatch):
    """Stub the engine. `calls` records (form_key, files); `values` is what it answers."""
    from app.services.ai_extract.extract_service import AIExtractService, ExtractResult

    state = {"values": {}, "calls": []}

    def fake(self, form_key, files, **kwargs):
        state["calls"].append((form_key, list(files)))
        return ExtractResult(values=dict(state["values"]))

    monkeypatch.setattr(AIExtractService, "extract", fake)
    return state


def _post(w, user, *, text="CONTOH pasted title", files=None, as_png=True):
    data = {"text": text} if text is not None else {}
    if files is None:
        files = [("files", ("site.png", PNG, "image/png"))] if as_png else []
    return as_user(w, user).post(AI_EXTRACT, data=data, files=files)


def _proposals(res) -> dict:
    body = res.json()
    return body.get("proposals", body)


def _status(p) -> str:
    return p["status"] if isinstance(p, dict) else "text"


def _seed(w):
    from app.models.lookup import LookupOption, LookupSet
    from app.models.order import Customer

    dev = developer(w.db, w.company_id, "CONTOH Developer Sdn Bhd")
    arch = developer(w.db, w.company_id, "CONTOH Architect Existing", "architect")
    builder = developer(w.db, w.company_id, "CONTOH Builder Existing", "main_contractor")
    kind = project_type(w.db, w.company_id, "Office")
    state = LookupSet(id=uid(), set_key="my_state", name="zzt my_state")
    w.db.add(state)
    w.db.flush()
    w.db.add(LookupOption(id=uid(), set_id=state.id, value="Johor", label="Johor", sort_order=1))
    for name in ("CONTOH Customer Alpha", "CONTOH Customer Twin", "CONTOH Customer Twin"):
        w.db.add(
            Customer(
                id=uid(), customer_code=f"ZZT-{uid()}", customer_name=name, company_id=w.company_id
            )
        )
    w.db.flush()
    return SimpleNs(dev=dev, arch=arch, builder=builder, kind=kind)


class SimpleNs:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# ------------------------------------------------------------------ C2 contract


def test_c2_without_projects_edit_the_route_is_403(v2, extracted):
    res = _post(v2, v2.approver)
    assert res.status_code == 403, res.text
    assert extracted["calls"] == []


def test_c2_a_disallowed_extension_is_422(v2, extracted):
    for name, mime in (("run.exe", "application/octet-stream"), ("clip.mp4", "video/mp4")):
        res = _post(v2, v2.owner, files=[("files", (name, b"x", mime))])
        assert res.status_code == 422, (name, res.text)
    assert extracted["calls"] == []


def test_c2_more_than_12_files_is_422(v2, extracted):
    files = [("files", (f"p{n}.png", PNG, "image/png")) for n in range(13)]
    res = _post(v2, v2.owner, files=files)
    assert res.status_code == 422, res.text
    assert extracted["calls"] == []


def test_c2_text_goes_to_the_engine_as_a_txt_file_under_the_registration_form_key(v2, extracted):
    res = _post(v2, v2.owner, text="Cadangan blok pejabat Lot 7001")
    assert res.status_code == 200, res.text
    (form_key, files), = extracted["calls"]
    assert form_key == FORM_KEY
    txt = [f for f in files if f.filename.lower().endswith(".txt")]
    assert len(txt) == 1 and txt[0].data == b"Cadangan blok pejabat Lot 7001"
    assert any(f.filename == "site.png" for f in files)


def test_c2_text_alone_and_photo_alone_are_both_accepted(v2, extracted):
    assert _post(v2, v2.owner, text="only text", files=[]).status_code == 200
    assert _post(v2, v2.owner, text=None).status_code == 200


# ------------------------------------------------------------------ C3 proposals


def test_c3_parties_match_by_type_ignoring_case_and_spacing_else_new(v2, extracted):
    seeded = _seed(v2)
    extracted["values"] = {
        "developer_name": "  contoh   DEVELOPER sdn bhd ",
        "architect_name": "CONTOH Architect Brand New",
        "main_contractor_name": "CONTOH Developer Sdn Bhd",  # exists, but only as a developer
    }
    res = _post(v2, v2.owner)
    assert res.status_code == 200, res.text
    got = _proposals(res)
    assert got["developer"]["status"] == "match"
    assert got["developer"]["id"] == seeded.dev.id
    assert got["developer"]["name"] == "CONTOH Developer Sdn Bhd"
    assert got["architect"] == {"status": "new", "name": "CONTOH Architect Brand New"}
    assert got["main_contractor"]["status"] == "new"


def test_c3_an_existing_architect_and_contractor_match(v2, extracted):
    seeded = _seed(v2)
    extracted["values"] = {
        "architect_name": "contoh architect existing",
        "main_contractor_name": "CONTOH Builder Existing",
    }
    got = _proposals(_post(v2, v2.owner))
    assert got["architect"]["status"] == "match" and got["architect"]["id"] == seeded.arch.id
    assert got["main_contractor"]["status"] == "match"
    assert got["main_contractor"]["id"] == seeded.builder.id


def test_c3_project_type_matches_by_name_else_not_found(v2, extracted):
    seeded = _seed(v2)
    extracted["values"] = {"type_of_building": "Office"}
    got = _proposals(_post(v2, v2.owner))
    assert got["project_type"]["status"] == "match" and got["project_type"]["id"] == seeded.kind.id
    extracted["values"] = {"type_of_building": "Castle"}
    assert _proposals(_post(v2, v2.owner))["project_type"]["status"] == "not_found"


def test_c3_state_resolves_through_the_my_state_lookup_else_not_found(v2, extracted):
    _seed(v2)
    extracted["values"] = {"state": "Johor"}
    got = _proposals(_post(v2, v2.owner))
    assert got["state"]["status"] == "match"
    assert "Johor" in json.dumps(got["state"])
    extracted["values"] = {"state": "Atlantis"}
    assert _proposals(_post(v2, v2.owner))["state"]["status"] == "not_found"


def test_c3_customer_matches_only_when_exactly_one_has_that_name_and_is_never_new(v2, extracted):
    _seed(v2)
    extracted["values"] = {"customer_name": "CONTOH Customer Alpha"}
    got = _proposals(_post(v2, v2.owner))
    assert got["customer"]["status"] == "match"
    assert got["customer"]["name"] == "CONTOH Customer Alpha" and got["customer"]["id"]
    for name in ("CONTOH Customer Twin", "CONTOH Customer Nobody"):
        extracted["values"] = {"customer_name": name}
        assert _proposals(_post(v2, v2.owner))["customer"]["status"] == "not_found", name


def test_c3_title_and_mukim_are_carried_as_text(v2, extracted):
    extracted["values"] = {"title": "CONTOH Kulai office block", "mukim": "Kulai"}
    got = _proposals(_post(v2, v2.owner))
    assert "CONTOH Kulai office block" in json.dumps(got["title"])
    assert "Kulai" in json.dumps(got["mukim"])


# ------------------------------------------------------------------ C4 writes nothing


def test_c4_nothing_is_created_for_new_or_matched_names(v2, extracted):
    from app.models.order import Customer
    from app.models.projects import Project, ProjectParty

    _seed(v2)
    extracted["values"] = {
        "developer_name": "CONTOH Developer Brand New",
        "architect_name": "CONTOH Architect Brand New",
        "customer_name": "CONTOH Customer Unknown",
        "title": "CONTOH Something",
    }

    def counts():
        v2.db.expire_all()
        return tuple(v2.db.query(m).count() for m in (Project, ProjectParty, Customer))

    before = counts()
    assert _post(v2, v2.owner).status_code == 200
    assert counts() == before


# ------------------------------------------------------------------ C5 rate limit, C6 provider


def test_c5_the_11th_call_in_ten_minutes_is_429_and_it_is_per_user(v2, extracted, clean_keys):
    for n in range(10):
        res = _post(v2, v2.owner)
        assert res.status_code != 429, (n, res.text)
    assert _post(v2, v2.owner).status_code == 429
    assert _post(v2, v2.sales_b).status_code != 429
    from app.services.queue_service import redis_conn

    try:
        for key in redis_conn.scan_iter(f"*{v2.sales_b}*"):
            redis_conn.delete(key)
    except Exception:  # noqa: BLE001
        pass


def test_c6_a_provider_failure_is_502_with_a_plain_message(v2, monkeypatch, clean_keys):
    from app.services.ai_extract import extract_service

    class Down:
        def chat(self, **kwargs):
            raise RuntimeError("zzt-provider-secret-trace")

    monkeypatch.setattr(
        extract_service.AIExtractService, "_resolve_provider", lambda self: (Down(), "openai", "gpt-4")
    )
    res = _post(v2, v2.owner)
    assert res.status_code == 502, res.text
    assert "zzt-provider-secret-trace" not in res.text


def test_c5b_files_over_the_total_size_cap_are_422(v2, extracted, monkeypatch):
    """The cap constant is lowered to 1 KB (the portal route's `_MAX_TOTAL_BYTES` and, should the
    staff route own one, the same name in the projects route module); 2 KB is sent."""
    from app.api.v1.projects import projects as staff_route
    from app.api.v1.public import ai_extract as portal_route

    monkeypatch.setattr(portal_route, "_MAX_TOTAL_BYTES", 1024)
    monkeypatch.setattr(staff_route, "_MAX_TOTAL_BYTES", 1024, raising=False)
    res = _post(v2, v2.owner, text=None, files=[("files", ("big.txt", b"x" * 2048, "text/plain"))])
    assert res.status_code == 422, res.text
    assert extracted["calls"] == []


def test_c6b_an_unexpected_error_gives_a_generic_message_without_the_exception_text(
    v2, monkeypatch, clean_keys
):
    from app.services.ai_extract.extract_service import AIExtractService

    def boom(self, form_key, files, **kwargs):
        raise ValueError("zzt-internal-trace-do-not-leak")

    monkeypatch.setattr(AIExtractService, "extract", boom)
    res = _post(v2, v2.owner)
    assert 500 <= res.status_code < 600, res.text
    assert "zzt-internal-trace-do-not-leak" not in res.text
