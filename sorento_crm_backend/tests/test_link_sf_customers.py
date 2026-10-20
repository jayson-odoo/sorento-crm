"""SF-CUSTOMER-LINK: the one-off script that links old Sponsorship Forms to their customer.

UAC: documentation/plans/procurement/sf-customer-link-acceptance-criteria.md (CL1-CL10).

`scripts/link_sf_customers.py` proposes a link per SF by exact (trimmed, whitespace-collapsed,
case-insensitive) name against ONE company's active customers, writes the proposal to a CSV for the
owner to review, and `--apply --from-csv` links only the reviewed LINK rows, re-checking each.

Blank Postgres schema, every row seeded here.
"""
from __future__ import annotations

import csv
import uuid

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.order import Customer
from app.models.procurement import PurchaseRequestHeader
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
from tests._pg_fixture import blank_session

SORENTO = frozenset({DEFAULT_COMPANY_ID})


@pytest.fixture
def db():
    register_company_scope_listeners()
    with blank_session() as s:
        yield s


def _code(prefix: str = "300") -> str:
    return f"{prefix}-ZZT{uuid.uuid4().hex[:6].upper()}"


def _customer(db, name, *, company_id=DEFAULT_COMPANY_ID, prefix="300", **kw) -> Customer:
    row = Customer(customer_code=_code(prefix), customer_name=name, company_id=company_id, **kw)
    db.add(row)
    db.flush()
    return row


def _sf(db, typed, *, request_type="sponsorship_form", **kw) -> str:
    row = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_type=request_type,
        request_number=f"ZZT-SF-{uuid.uuid4().hex[:6]}",
        customer_name=typed,
        **kw,
    )
    db.add(row)
    db.flush()
    return row.id


@pytest.fixture
def scenario(db):
    """Every case the script must tell apart, in the default company (Sorento)."""
    set_company_scope(db, None)  # seed both companies
    seed_mocha(db)
    alpha = _customer(db, "ZZT ALPHA SDN BHD", debtor_type="project")
    beta = _customer(db, "ZZT BETA (PROJECT)", prefix="302", debtor_type="project_cash")
    twin_a = _customer(db, "ZZT TWIN SDN BHD", debtor_type="project")
    twin_b = _customer(db, "zzt twin sdn bhd", debtor_type="project")
    _customer(db, "ZZT GHOST SDN BHD", is_active=False)
    _customer(db, "ZZT HALF SDN BHD", is_active=False)
    half = _customer(db, "ZZT HALF SDN BHD", prefix="301", debtor_type="cash_sales")
    both = _customer(db, "ZZT BOTH SDN BHD", debtor_type="project")
    _customer(db, "ZZT BOTH SDN BHD", company_id=MOCHA_ID, debtor_type="project")
    _customer(db, "ZZT MOCHA ONLY SDN BHD", company_id=MOCHA_ID, debtor_type="project")
    _customer(db, "   ", debtor_type="project")  # a blank-named customer never matches a blank SF
    ids = {
        "link_spaced": _sf(db, "  zzt   alpha\tsdn  bhd "),
        "link_suffix_as_stored": _sf(db, "zzt beta (project)"),
        "link_inactive_twin_ignored": _sf(db, "ZZT HALF SDN BHD"),
        "link_other_company_twin_ignored": _sf(db, "ZZT BOTH SDN BHD"),
        "ambiguous": _sf(db, "ZZT TWIN SDN BHD"),
        "no_match_text": _sf(db, "ZZT NOBODY SDN BHD"),
        "no_match_suffix_added": _sf(db, "ZZT ALPHA SDN BHD (PROJECT)"),
        "no_match_prefix_only": _sf(db, "ZZT ALPHA"),
        "no_match_blank": _sf(db, "   "),
        "no_match_null": _sf(db, None),
        "no_match_inactive_only": _sf(db, "ZZT GHOST SDN BHD"),
        "no_match_other_company_only": _sf(db, "ZZT MOCHA ONLY SDN BHD"),
        "already_linked": _sf(db, "SOMETHING ELSE TYPED", customer_id=alpha.id),
        "purchase_request": _sf(db, "ZZT ALPHA SDN BHD", request_type="purchase_request"),
    }
    db.commit()
    set_company_scope(db, SORENTO)  # the CLI runs scoped to the one company it matches in
    return {
        "ids": ids,
        "alpha": alpha,
        "beta": beta,
        "half": half,
        "both": both,
        "twins": {twin_a.customer_code, twin_b.customer_code},
    }


def _stored(db, sf_id) -> tuple:
    return tuple(
        db.execute(
            text("SELECT customer_id::text, customer_name, sales_type FROM purchase_requests WHERE id = :i"),
            {"i": sf_id},
        ).one()
    )


def _snapshot(db, ids) -> dict:
    return {k: _stored(db, v) for k, v in ids.items()}


def _by_sf(rows) -> dict:
    return {r["sf_id"]: r for r in rows}


def _write(path, rows):
    from scripts.link_sf_customers import write_csv

    write_csv(rows, str(path))
    return path


def _read_csv(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:  # the proposal carries a BOM
        return list(csv.DictReader(fh))


def _rewrite_csv(path, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# --- CL2-CL6: the proposal --------------------------------------------------- #


def test_propose_gives_each_sponsorship_form_exactly_one_status(db, scenario):
    from scripts.link_sf_customers import propose

    ids = scenario["ids"]
    rows = _by_sf(propose(db, DEFAULT_COMPANY_ID))

    assert ids["purchase_request"] not in rows  # CL1: SFs only
    assert {k: rows[v]["status"] for k, v in ids.items() if k != "purchase_request"} == {
        "link_spaced": "LINK",
        "link_suffix_as_stored": "LINK",
        "link_inactive_twin_ignored": "LINK",
        "link_other_company_twin_ignored": "LINK",
        "ambiguous": "AMBIGUOUS",
        "no_match_text": "NO MATCH",
        "no_match_suffix_added": "NO MATCH",
        "no_match_prefix_only": "NO MATCH",
        "no_match_blank": "NO MATCH",
        "no_match_null": "NO MATCH",
        "no_match_inactive_only": "NO MATCH",
        "no_match_other_company_only": "NO MATCH",
        "already_linked": "ALREADY LINKED",
    }


def test_link_row_names_the_one_matched_customer_and_the_sales_type_it_maps_to(db, scenario):
    from scripts.link_sf_customers import propose

    ids = scenario["ids"]
    rows = _by_sf(propose(db, DEFAULT_COMPANY_ID))

    spaced = rows[ids["link_spaced"]]
    assert spaced["typed_customer"] == "  zzt   alpha\tsdn  bhd "
    assert spaced["customer_id"] == str(scenario["alpha"].id)
    assert spaced["customer_code"] == scenario["alpha"].customer_code
    assert spaced["customer_name"] == "ZZT ALPHA SDN BHD"
    assert spaced["debtor_type"] == "project"
    assert spaced["sales_type"] == "project"

    suffix = rows[ids["link_suffix_as_stored"]]
    assert suffix["customer_id"] == str(scenario["beta"].id)
    assert suffix["debtor_type"] == "project_cash"
    assert suffix["sales_type"] == "cash_sales"

    assert rows[ids["link_inactive_twin_ignored"]]["customer_id"] == str(scenario["half"].id)
    # The Mocha customer with the same name is invisible: the Sorento one links, not AMBIGUOUS.
    assert rows[ids["link_other_company_twin_ignored"]]["customer_id"] == str(scenario["both"].id)


def test_ambiguous_lists_every_candidate_code_and_picks_none(db, scenario):
    from scripts.link_sf_customers import propose

    row = _by_sf(propose(db, DEFAULT_COMPANY_ID))[scenario["ids"]["ambiguous"]]

    assert row["customer_id"] == ""
    assert set(row["customer_code"].split("; ")) == scenario["twins"]


def test_already_linked_shows_the_linked_customer(db, scenario):
    from scripts.link_sf_customers import propose

    row = _by_sf(propose(db, DEFAULT_COMPANY_ID))[scenario["ids"]["already_linked"]]

    assert row["customer_id"] == str(scenario["alpha"].id)
    assert row["customer_code"] == scenario["alpha"].customer_code
    assert row["typed_customer"] == "SOMETHING ELSE TYPED"


def test_other_company_scope_matches_only_that_company(db, scenario):
    from scripts.link_sf_customers import propose

    set_company_scope(db, frozenset({MOCHA_ID}))
    rows = _by_sf(propose(db, MOCHA_ID))
    ids = scenario["ids"]

    assert rows[ids["no_match_other_company_only"]]["status"] == "LINK"
    assert rows[ids["link_spaced"]]["status"] == "NO MATCH"  # alpha is a Sorento customer


def test_company_filter_holds_even_with_an_all_companies_scope(db, scenario):
    from scripts.link_sf_customers import propose

    set_company_scope(db, None)
    rows = _by_sf(propose(db, DEFAULT_COMPANY_ID))
    ids = scenario["ids"]

    assert rows[ids["no_match_other_company_only"]]["status"] == "NO MATCH"
    assert rows[ids["link_other_company_twin_ignored"]]["customer_id"] == str(scenario["both"].id)


# --- CL1: the dry run -------------------------------------------------------- #


def test_dry_run_writes_the_csv_and_nothing_to_the_database(db, scenario, tmp_path):
    from scripts.link_sf_customers import CSV_FIELDS, propose

    ids = scenario["ids"]
    before = _snapshot(db, ids)
    path = _write(tmp_path / "proposal.csv", propose(db, DEFAULT_COMPANY_ID))

    assert _snapshot(db, ids) == before
    rows = _read_csv(path)
    assert list(rows[0].keys()) == list(CSV_FIELDS)
    assert len(rows) == len(ids) - 1  # every SF, no PR
    assert {r["sf_id"] for r in rows} == {v for k, v in ids.items() if k != "purchase_request"}


# --- CL7-CL10: apply from the reviewed CSV ------------------------------------ #


def test_apply_links_only_the_link_rows_left_in_the_csv(db, scenario, tmp_path):
    from scripts.link_sf_customers import apply_csv, propose

    ids = scenario["ids"]
    path = _write(tmp_path / "proposal.csv", propose(db, DEFAULT_COMPANY_ID))
    # The owner deletes one LINK row to skip it.
    _rewrite_csv(path, [r for r in _read_csv(path) if r["sf_id"] != ids["link_other_company_twin_ignored"]])
    before = _snapshot(db, ids)

    result = apply_csv(db, str(path), DEFAULT_COMPANY_ID)

    assert result["linked"] == 3
    after = _snapshot(db, ids)
    assert after["link_spaced"][:2] == (str(scenario["alpha"].id), "ZZT ALPHA SDN BHD")
    assert after["link_suffix_as_stored"][:2] == (str(scenario["beta"].id), "ZZT BETA (PROJECT)")
    assert after["link_inactive_twin_ignored"][:2] == (str(scenario["half"].id), "ZZT HALF SDN BHD")
    unchanged = [k for k in ids if k not in ("link_spaced", "link_suffix_as_stored", "link_inactive_twin_ignored")]
    assert {k: after[k] for k in unchanged} == {k: before[k] for k in unchanged}
    # Sales type is the backfill script's job, not this one's.
    assert all(after[k][2] is None for k in ids)


def test_apply_refuses_a_row_the_owner_hand_marked_link(db, scenario, tmp_path):
    """A CSV row typed in as LINK with a customer the match never proposed is not linked."""
    from scripts.link_sf_customers import apply_csv, propose

    ids = scenario["ids"]
    path = _write(tmp_path / "proposal.csv", propose(db, DEFAULT_COMPANY_ID))
    rows = _read_csv(path)
    for r in rows:
        if r["sf_id"] in (ids["ambiguous"], ids["no_match_text"]):
            r["status"] = "LINK"
            r["customer_id"] = str(scenario["alpha"].id)
        if r["sf_id"] == ids["link_spaced"]:  # a LINK row pointed at another customer
            r["customer_id"] = str(scenario["beta"].id)
    # A Purchase Request typed in as a LINK row exactly as the proposal would show it (its name
    # matches alpha): only Sponsorship Forms are ever linked.
    pr_number = db.execute(
        text("SELECT request_number FROM purchase_requests WHERE id = :i"), {"i": ids["purchase_request"]}
    ).scalar()
    alpha_row = next(r for r in rows if r["sf_id"] == ids["link_spaced"])
    rows.append(
        dict(
            alpha_row,
            customer_id=str(scenario["alpha"].id),
            sf_id=ids["purchase_request"],
            form_number=pr_number,
            typed_customer="ZZT ALPHA SDN BHD",
        )
    )
    _rewrite_csv(path, rows)

    result = apply_csv(db, str(path), DEFAULT_COMPANY_ID)

    assert result["linked"] == 3
    assert result["skipped_changed"] == 4
    assert _stored(db, ids["ambiguous"])[0] is None
    assert _stored(db, ids["no_match_text"])[0] is None
    assert _stored(db, ids["link_spaced"])[0] is None
    assert _stored(db, ids["purchase_request"])[0] is None


def test_apply_skips_a_link_row_whose_customer_columns_were_edited(db, scenario, tmp_path):
    """The owner 'corrects' a LINK row to another customer by code/name: it is not linked at all."""
    from scripts.link_sf_customers import apply_csv, propose

    ids = scenario["ids"]
    path = _write(tmp_path / "proposal.csv", propose(db, DEFAULT_COMPANY_ID))
    rows = _read_csv(path)
    for r in rows:
        if r["sf_id"] == ids["link_spaced"]:
            r["customer_code"] = scenario["beta"].customer_code
        if r["sf_id"] == ids["link_suffix_as_stored"]:
            r["customer_name"] = "ZZT ALPHA SDN BHD"
    _rewrite_csv(path, rows)

    result = apply_csv(db, str(path), DEFAULT_COMPANY_ID)

    assert result["linked"] == 2
    assert result["skipped_changed"] == 2
    assert _stored(db, ids["link_spaced"])[0] is None
    assert _stored(db, ids["link_suffix_as_stored"])[0] is None


def test_apply_refuses_a_csv_that_lists_a_form_twice(db, scenario, tmp_path):
    """Two rows for one SF (one kept as LINK, one changed to skip it) is a review mistake, not a choice."""
    from scripts.link_sf_customers import apply_csv, propose

    ids = scenario["ids"]
    path = _write(tmp_path / "proposal.csv", propose(db, DEFAULT_COMPANY_ID))
    rows = _read_csv(path)
    twice = next(r for r in rows if r["sf_id"] == ids["link_spaced"])
    rows.append(dict(twice, status="SKIP"))
    _rewrite_csv(path, rows)

    with pytest.raises(ValueError):
        apply_csv(db, str(path), DEFAULT_COMPANY_ID)
    assert _stored(db, ids["link_spaced"])[0] is None


def test_csv_cells_never_start_a_spreadsheet_formula_and_still_apply(db, scenario, tmp_path):
    """Typed text comes from portal SFs; the owner opens the CSV in a spreadsheet."""
    from scripts.link_sf_customers import apply_csv, propose

    set_company_scope(db, None)
    dash = _customer(db, "-ZZT DASH CO", debtor_type="project")
    dash_sf = _sf(db, "-zzt dash co")
    formula_sf = _sf(db, '=HYPERLINK("http://x.zzt","ZZT")')
    db.commit()
    set_company_scope(db, SORENTO)
    path = _write(tmp_path / "proposal.csv", propose(db, DEFAULT_COMPANY_ID))

    by_sf = {r["sf_id"]: r for r in _read_csv(path)}
    assert by_sf[formula_sf]["typed_customer"] == "'" + '=HYPERLINK("http://x.zzt","ZZT")'
    assert by_sf[dash_sf]["typed_customer"] == "'-zzt dash co"
    assert by_sf[dash_sf]["customer_name"] == "'-ZZT DASH CO"
    for r in _read_csv(path):
        assert not any((v or "")[:1] in ("=", "+", "-", "@") for v in r.values())

    apply_csv(db, str(path), DEFAULT_COMPANY_ID)
    assert _stored(db, dash_sf)[:2] == (str(dash.id), "-ZZT DASH CO")


def test_default_proposal_csv_is_written_outside_the_working_directory():
    """The prod compose directory is a git checkout: real names must not land in it by default."""
    import os
    import tempfile

    from scripts.link_sf_customers import DEFAULT_CSV

    assert os.path.dirname(DEFAULT_CSV) == tempfile.gettempdir()


def test_apply_never_overwrites_and_skips_rows_that_changed_since_the_dry_run(db, scenario, tmp_path):
    from scripts.link_sf_customers import apply_csv, propose

    ids = scenario["ids"]
    path = _write(tmp_path / "proposal.csv", propose(db, DEFAULT_COMPANY_ID))
    # After the review: staff link one SF by hand to another customer, retype another, and the
    # third's customer is deactivated.
    set_company_scope(db, None)
    db.execute(
        text("UPDATE purchase_requests SET customer_id = :c WHERE id = :i"),
        {"c": str(scenario["both"].id), "i": ids["link_spaced"]},
    )
    db.execute(
        text("UPDATE purchase_requests SET customer_name = 'ZZT BETA' WHERE id = :i"),
        {"i": ids["link_suffix_as_stored"]},
    )
    db.execute(text("UPDATE customers SET is_active = false WHERE id = :i"), {"i": str(scenario["half"].id)})
    db.commit()
    db.expire_all()
    set_company_scope(db, SORENTO)

    result = apply_csv(db, str(path), DEFAULT_COMPANY_ID)

    assert result["linked"] == 1  # only the other-company-twin row is still exactly as reviewed
    assert result["skipped_already_linked"] == 1
    assert result["skipped_changed"] == 2
    # The operator sees WHICH reviewed rows were not linked, by form number.
    numbers = {
        k: db.execute(text("SELECT request_number FROM purchase_requests WHERE id = :i"), {"i": ids[k]}).scalar()
        for k in ("link_spaced", "link_suffix_as_stored", "link_inactive_twin_ignored")
    }
    assert sorted(result["skipped_forms"]) == sorted(numbers.values())
    assert _stored(db, ids["link_spaced"])[0] == str(scenario["both"].id)
    assert _stored(db, ids["link_suffix_as_stored"])[0] is None
    assert _stored(db, ids["link_inactive_twin_ignored"])[0] is None
    assert _stored(db, ids["already_linked"])[:2] == (str(scenario["alpha"].id), "SOMETHING ELSE TYPED")


def test_apply_is_idempotent(db, scenario, tmp_path):
    from scripts.link_sf_customers import apply_csv, propose

    path = _write(tmp_path / "proposal.csv", propose(db, DEFAULT_COMPANY_ID))
    first = apply_csv(db, str(path), DEFAULT_COMPANY_ID)
    snapshot = _snapshot(db, scenario["ids"])

    again = apply_csv(db, str(path), DEFAULT_COMPANY_ID)

    assert first["linked"] == 4
    assert again["linked"] == 0
    assert again["skipped_already_linked"] == 4
    assert _snapshot(db, scenario["ids"]) == snapshot


def test_apply_commits_all_links_or_none(db, scenario, tmp_path, monkeypatch):
    import scripts.link_sf_customers as script

    path = _write(tmp_path / "proposal.csv", script.propose(db, DEFAULT_COMPANY_ID))
    real = script.link_customer
    calls = []

    def flaky(session, raw, current_id=None):
        calls.append(raw)
        if len(calls) == 3:
            raise RuntimeError("boom")
        return real(session, raw, current_id=current_id)

    monkeypatch.setattr(script, "link_customer", flaky)
    with pytest.raises(RuntimeError):
        script.apply_csv(db, str(path), DEFAULT_COMPANY_ID)

    db.expire_all()
    linkable = ("link_spaced", "link_suffix_as_stored", "link_inactive_twin_ignored", "link_other_company_twin_ignored")
    assert all(_stored(db, scenario["ids"][k])[0] is None for k in linkable)


def test_apply_refuses_a_csv_without_the_key_columns(db, scenario, tmp_path):
    from scripts.link_sf_customers import apply_csv

    path = tmp_path / "bad.csv"
    path.write_text("status,form_number\nLINK,ZZT-1\n", encoding="utf-8")

    with pytest.raises(ValueError):
        apply_csv(db, str(path), DEFAULT_COMPANY_ID)


def test_apply_refuses_a_csv_missing_any_proposal_column(db, scenario, tmp_path):
    """Every column is compared, so a file without one (here customer_code) is not a reviewed proposal."""
    from scripts.link_sf_customers import apply_csv, propose

    path = _write(tmp_path / "proposal.csv", propose(db, DEFAULT_COMPANY_ID))
    _rewrite_csv(path, [{k: v for k, v in r.items() if k != "customer_code"} for r in _read_csv(path)])

    with pytest.raises(ValueError):
        apply_csv(db, str(path), DEFAULT_COMPANY_ID)
    assert _stored(db, scenario["ids"]["link_spaced"])[0] is None


def test_apply_refuses_a_form_listed_twice_in_another_case(db, scenario, tmp_path):
    from scripts.link_sf_customers import apply_csv, propose

    ids = scenario["ids"]
    path = _write(tmp_path / "proposal.csv", propose(db, DEFAULT_COMPANY_ID))
    rows = _read_csv(path)
    twice = next(r for r in rows if r["sf_id"] == ids["link_spaced"])
    rows.append(dict(twice, status="SKIP", sf_id=twice["sf_id"].upper()))
    _rewrite_csv(path, rows)

    with pytest.raises(ValueError):
        apply_csv(db, str(path), DEFAULT_COMPANY_ID)
    assert _stored(db, ids["link_spaced"])[0] is None


def test_apply_locks_the_forms_it_links(db, scenario, tmp_path):
    """A staff link saved during the run waits for this commit instead of being overwritten."""
    from sqlalchemy import event

    from scripts.link_sf_customers import apply_csv, propose

    path = _write(tmp_path / "proposal.csv", propose(db, DEFAULT_COMPANY_ID))
    seen: list = []
    conn = db.connection()
    listener = lambda *a, **k: seen.append(a[2])  # noqa: E731 - (conn, cursor, statement, ...)
    event.listen(conn, "before_cursor_execute", listener)
    try:
        apply_csv(db, str(path), DEFAULT_COMPANY_ID)
    finally:
        event.remove(conn, "before_cursor_execute", listener)

    assert any("FOR UPDATE OF" in stmt and "purchase_requests" in stmt for stmt in seen)


def test_proposal_csv_opens_as_utf8_in_a_spreadsheet_and_only_its_owner_can_read_it(db, scenario, tmp_path):
    """Excel reads a CSV without a BOM in the local code page; the file holds real customer names."""
    import os
    import stat

    from scripts.link_sf_customers import propose

    path = _write(tmp_path / "proposal.csv", propose(db, DEFAULT_COMPANY_ID))

    assert path.read_bytes()[:3] == b"\xef\xbb\xbf"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


# --- CLI ---------------------------------------------------------------------- #


def _patch_session(monkeypatch, db, registered=None):
    import scripts.link_sf_customers as script

    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(script, "SessionLocal", lambda: db)
    # The audit listeners are global on Session: spy instead of registering them for the whole run.
    calls = registered if registered is not None else []
    monkeypatch.setattr(script, "register_audit_listeners", lambda: calls.append("audit"))
    monkeypatch.setattr(script, "register_company_scope_listeners", lambda: calls.append("company_scope"))
    return script


def test_cli_registers_the_company_scope_and_audit_listeners(db, scenario, tmp_path, monkeypatch):
    """A script process has no app startup: without these the scope is a no-op and the links leave no audit."""
    registered: list = []
    script = _patch_session(monkeypatch, db, registered)

    assert script.main(["--csv", str(tmp_path / "proposal.csv")]) == 0

    assert set(registered) == {"audit", "company_scope"}


def test_cli_dry_run_then_apply_then_points_at_the_sales_type_backfill(db, scenario, tmp_path, monkeypatch, capsys):
    script = _patch_session(monkeypatch, db)
    path = tmp_path / "proposal.csv"
    before = _snapshot(db, scenario["ids"])

    assert script.main(["--csv", str(path)]) == 0
    dry = capsys.readouterr().out
    assert _snapshot(db, scenario["ids"]) == before
    assert len(_read_csv(path)) == len(scenario["ids"]) - 1
    assert "LINK: 4" in dry and "NO MATCH: 7" in dry and "AMBIGUOUS: 1" in dry and "ALREADY LINKED: 1" in dry

    assert script.main(["--apply", "--from-csv", str(path)]) == 0
    applied = capsys.readouterr().out
    assert "Linked: 4" in applied
    assert "Not linked: none" in applied
    assert "scripts/backfill_sf_sales_type.py" in applied
    assert _stored(db, scenario["ids"]["link_spaced"])[0] == str(scenario["alpha"].id)


def test_cli_apply_needs_the_reviewed_csv(db, monkeypatch):
    script = _patch_session(monkeypatch, db)

    with pytest.raises(SystemExit) as exc:
        script.main(["--apply"])
    assert exc.value.code == 2
