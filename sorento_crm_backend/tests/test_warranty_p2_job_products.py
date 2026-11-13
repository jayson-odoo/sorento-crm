"""AFTER-SALES-P2 red tests: service job product lines and the warranty answers on a job (UAC J1-J10, P3).

Wire contract the coder implements (under /api/v1/after-sales/service-jobs/{id}):

* products   GET -> plain list ordered by sort_order then creation; POST 201 {product_id, kind_id?,
             purchase_date?, defect_type_id?}; PATCH|DELETE products/{line_id} (200). A line row carries
             id, product_id, product_code, product_name, kind_id, kind_name, purchase_date,
             defect_type_id, defect_label. PATCH only changes the fields it sends.
* job GET    gains `warranty`: [{id, product_code, product_name, kind_name, purchase_date, defect_label,
             verdicts: [{part_name, verdict, expiry, reason, is_lifetime, installation_included,
             policy_version}]}], computed at read time, [] when the job has no lines.
* job list   rows gain `warranty_summary`; filter `warranty_summary` (repeatable or comma); sort key
             `warranty_summary`, asc order: covered, partly_covered, not_covered, unknown, null (desc reversed).
* "today"    for the future-date check is `app.services.warranty_service.warranty_today()` (frozen here).
* audit      ServiceJobProduct has `__audit_parent__ = "service_job_id"`: its rows have entity_type
             "service_job_products", root_entity_type "service_jobs", root_entity_id the job id.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from ._service_jobs_p1_support import make_job
from ._warranty_p2_support import (
    BA,
    CB,
    JOBS,
    VIEW,
    WC,
    add_line,
    api,
    defect,
    env,  # noqa: F401
    foreign_defect,
    kind_by_code,
    line_audit,
    make_company,
    make_kind,
    make_policy,
    make_product,
    make_rule,
    make_term,
    seed_v15,
    today,  # noqa: F401
)

BOUGHT = date(2020, 3, 15)
D = date


def lines_url(job_id):
    return f"{JOBS}/{job_id}/products"


def job_with_policy_kinds(env):
    """An open-ended policy and four kinds: lifetime only, lifetime + 12 months, 12 months only, no term."""
    policy = make_policy(env)
    life, mix, exp, bare = (make_kind(env) for _ in range(4))
    make_term(env, policy, life, "Body", lifetime=True)
    make_term(env, policy, mix, "Body", lifetime=True)
    make_term(env, policy, mix, "Fit", months=12)
    make_term(env, policy, exp, "Fit", months=12)
    return dict(life=life, mix=mix, exp=exp, none=bare)


def summary_of(client, job):
    rows = client.get(JOBS, params={"query": job.customer_name, "limit": 50}).json()["data"]
    (row,) = [r for r in rows if r["id"] == job.id]
    return row["warranty_summary"]


# ------------------------------------------------------------------ J1 / J2 lines


def test_j1_add_list_edit_and_delete_a_line(env, today):
    product = make_product(env, *WC)
    job = make_job(env)
    with api(env) as c:
        r = add_line(c, job.id, product.id, purchase_date="2020-03-15")
        assert r.status_code == 201, r.text
        line = r.json()
        assert (line["product_id"], line["product_code"], line["purchase_date"]) == (product.id, WC[0], "2020-03-15")
        rows = c.get(lines_url(job.id)).json()
        assert [x["id"] for x in rows] == [line["id"]]
        patched = c.patch(f"{lines_url(job.id)}/{line['id']}", json={"purchase_date": "2021-01-02"})
        assert patched.status_code == 200 and patched.json()["purchase_date"] == "2021-01-02"
        assert c.delete(f"{lines_url(job.id)}/{line['id']}").status_code == 200
        assert c.get(lines_url(job.id)).json() == []


def test_j1_delete_is_a_hard_delete(env, today):
    from app.models.service_jobs import ServiceJobProduct

    product, job = make_product(env, *WC), make_job(env)
    with api(env) as c:
        line_id = add_line(c, job.id, product.id).json()["id"]
        c.delete(f"{lines_url(job.id)}/{line_id}")
    env.db.expire_all()
    assert env.db.query(ServiceJobProduct).filter(ServiceJobProduct.id == line_id).count() == 0


def test_j1_lines_come_back_in_the_order_they_were_added_and_only_for_their_job(env, today):
    p1, p2 = make_product(env, *WC), make_product(env, *CB)
    job, other = make_job(env), make_job(env)
    with api(env) as c:
        first = add_line(c, job.id, p1.id).json()["id"]
        second = add_line(c, job.id, p2.id).json()["id"]
        add_line(c, other.id, p1.id)
        assert [x["id"] for x in c.get(lines_url(job.id)).json()] == [first, second]
        assert len(c.get(lines_url(other.id)).json()) == 1


def test_j1_a_line_of_another_job_is_404_and_so_is_an_unknown_job(env, today):
    product = make_product(env, *WC)
    job, other = make_job(env), make_job(env)
    with api(env) as c:
        line_id = add_line(c, other.id, product.id).json()["id"]
        assert c.patch(f"{lines_url(job.id)}/{line_id}", json={"purchase_date": "2021-01-01"}).status_code == 404
        assert c.delete(f"{lines_url(job.id)}/{line_id}").status_code == 404
        ghost = str(uuid.uuid4())
        assert c.get(lines_url(ghost)).status_code == 404
        assert add_line(c, ghost, product.id).status_code == 404


def test_j1_defect_and_kind_must_be_real_options(env, today):
    product, job = make_product(env, *WC), make_job(env)
    with api(env) as c:
        assert add_line(c, job.id, product.id, defect_type_id=str(uuid.uuid4())).status_code == 422
        assert add_line(c, job.id, product.id, defect_type_id=foreign_defect(env)).status_code == 422
        assert add_line(c, job.id, product.id, kind_id=str(uuid.uuid4())).status_code == 422
        ok = add_line(c, job.id, product.id, defect_type_id=defect(env, "Leakage"))
        assert ok.status_code == 201 and ok.json()["defect_label"] == "Leakage"


def test_j2_a_missing_or_unknown_product_is_422(env, today):
    job = make_job(env)
    with api(env) as c:
        assert c.post(lines_url(job.id), json={"purchase_date": "2020-03-15"}).status_code == 422
        assert c.post(lines_url(job.id), json={"product_id": None}).status_code == 422
        assert add_line(c, job.id, str(uuid.uuid4())).status_code == 422
        assert c.post(lines_url(job.id), json={"product_name": "free text kettle"}).status_code == 422


def test_j2_a_product_of_another_company_is_422(env, today):
    theirs = make_product(env, "ZZT-OTHER-CO", "ZZ-CAT", company_id=make_company(env))
    job = make_job(env)
    with api(env) as c:
        assert add_line(c, job.id, theirs.id).status_code == 422


# ------------------------------------------------------------------ J3 / J4 / J5 / J6


def test_j3_a_future_purchase_date_is_422_on_create_and_edit_but_today_is_fine(env, today):
    product, job = make_product(env, *WC), make_job(env)
    with api(env) as c:
        r = add_line(c, job.id, product.id, purchase_date="2026-11-14")
        assert r.status_code == 422
        assert "Purchase date cannot be in the future" in r.text
        ok = add_line(c, job.id, product.id, purchase_date="2026-11-13")
        assert ok.status_code == 201
        edit = c.patch(f"{lines_url(job.id)}/{ok.json()['id']}", json={"purchase_date": "2027-01-01"})
        assert edit.status_code == 422 and "Purchase date cannot be in the future" in edit.text


def test_j4_a_kind_not_sent_is_suggested_from_the_rules_and_stored(env, today):
    kind = make_kind(env, "water_closet_t")
    make_rule(env, kind, "category", WC[1])
    wc, cb = make_product(env, *WC), make_product(env, *CB)
    job = make_job(env)
    with api(env) as c:
        suggested = add_line(c, job.id, wc.id).json()
        assert suggested["kind_id"] == kind.id
        assert add_line(c, job.id, cb.id).json()["kind_id"] is None
        stored = [x for x in c.get(lines_url(job.id)).json() if x["id"] == suggested["id"]][0]
        assert stored["kind_id"] == kind.id


def test_j4_a_kind_sent_by_cs_is_kept_and_a_later_edit_does_not_re_suggest(env, today):
    suggested_kind, chosen = make_kind(env), make_kind(env)
    make_rule(env, suggested_kind, "category", WC[1])
    wc, job = make_product(env, *WC), make_job(env)
    with api(env) as c:
        line = add_line(c, job.id, wc.id, kind_id=chosen.id).json()
        assert line["kind_id"] == chosen.id
        after = c.patch(f"{lines_url(job.id)}/{line['id']}", json={"purchase_date": "2021-05-05"}).json()
        assert after["kind_id"] == chosen.id
        again = c.patch(f"{lines_url(job.id)}/{line['id']}", json={"defect_type_id": defect(env, "Rust")}).json()
        assert again["kind_id"] == chosen.id


def test_j4_a_line_saved_without_a_suggestion_stays_without_a_kind_on_edit(env, today):
    cb, job = make_product(env, *CB), make_job(env)
    with api(env) as c:
        line = add_line(c, job.id, cb.id).json()
        assert line["kind_id"] is None
        assert c.patch(f"{lines_url(job.id)}/{line['id']}", json={"purchase_date": "2021-05-05"}).json()["kind_id"] is None


def test_j5_the_same_product_can_be_on_two_lines(env, today):
    product, job = make_product(env, *WC), make_job(env)
    with api(env) as c:
        assert add_line(c, job.id, product.id).status_code == 201
        assert add_line(c, job.id, product.id).status_code == 201
        assert len(c.get(lines_url(job.id)).json()) == 2


def test_j6_an_archived_kind_cannot_be_set_on_a_new_line_or_changed_to(env, today):
    archived, live = make_kind(env, active=False), make_kind(env)
    product, job = make_product(env, *WC), make_job(env)
    with api(env) as c:
        assert add_line(c, job.id, product.id, kind_id=archived.id).status_code == 422
        line = add_line(c, job.id, product.id, kind_id=live.id).json()
        assert c.patch(f"{lines_url(job.id)}/{line['id']}", json={"kind_id": archived.id}).status_code == 422


def test_j6_a_line_that_already_has_a_kind_keeps_it_and_its_verdicts_after_the_kind_is_archived(env, today):
    kinds = job_with_policy_kinds(env)
    product, job = make_product(env, *WC), make_job(env)
    with api(env) as c:
        line = add_line(c, job.id, product.id, kind_id=kinds["life"].id, purchase_date="2020-03-15").json()
        c.patch(f"/api/v1/after-sales/warranty/kinds/{kinds['life'].id}", json={"is_active": False})
        got = c.get(f"{JOBS}/{job.id}").json()["warranty"][0]
        assert [v["verdict"] for v in got["verdicts"]] == ["covered"]
        assert [x["kind_id"] for x in c.get(lines_url(job.id)).json()] == [kinds["life"].id]
        assert c.patch(f"{lines_url(job.id)}/{line['id']}", json={"purchase_date": "2020-04-01"}).status_code == 200


def test_j6_an_archived_kind_is_never_suggested(env, today):
    archived = make_kind(env, active=False)
    make_rule(env, archived, "category", WC[1])
    product, job = make_product(env, *WC), make_job(env)
    with api(env) as c:
        assert add_line(c, job.id, product.id).json()["kind_id"] is None


# ------------------------------------------------------------------ J7 cascade


def test_j7_deleting_a_job_deletes_its_lines(env, today):
    from app.models.service_jobs import ServiceJobProduct

    product, job = make_product(env, *WC), make_job(env)
    with api(env) as c:
        add_line(c, job.id, product.id)
        add_line(c, job.id, product.id)
    env.db.execute(text("delete from service_jobs where id = :i"), {"i": job.id})
    env.db.expire_all()
    assert env.db.query(ServiceJobProduct).filter(ServiceJobProduct.service_job_id == job.id).count() == 0


# ------------------------------------------------------------------ J8 warranty on the job


def test_j8_the_job_carries_per_line_fields_and_verdicts_from_the_v15_policy(env, today):
    seed_v15(env)
    make_rule(env, kind_by_code(env, "water_closet"), "category", WC[1])
    product, job = make_product(env, *WC, name="ZZT Water Closet"), make_job(env)
    with api(env) as c:
        add_line(c, job.id, product.id, purchase_date="2020-03-15", defect_type_id=defect(env, "Leakage"))
        warranty = c.get(f"{JOBS}/{job.id}").json()["warranty"]
    assert len(warranty) == 1
    line = warranty[0]
    assert (line["product_code"], line["product_name"], line["kind_name"], line["purchase_date"], line["defect_label"]) == (
        WC[0], "ZZT Water Closet", "Water Closet", "2020-03-15", "Leakage",
    )
    by_part = {v["part_name"]: v for v in line["verdicts"]}
    assert len(by_part) == 3
    assert (by_part["Ceramic Body"]["verdict"], by_part["Ceramic Body"]["is_lifetime"]) == ("covered", True)
    fit = by_part["Flushing Fittings"]
    assert (fit["verdict"], fit["expiry"], fit["policy_version"]) == ("expired", "2025-03-15", "v15")
    assert "5 years from 15/03/2020" in fit["reason"]
    assert set(fit) >= {"part_name", "verdict", "expiry", "reason", "is_lifetime", "installation_included", "policy_version"}


def test_j8_a_line_with_no_kind_reads_unknown_no_warranty_rule_and_no_lines_is_empty(env, today):
    seed_v15(env)
    cb, job, empty = make_product(env, *CB), make_job(env), make_job(env)
    with api(env) as c:
        add_line(c, job.id, cb.id, purchase_date="2020-03-15")
        (line,) = c.get(f"{JOBS}/{job.id}").json()["warranty"]
        assert [v["verdict"] for v in line["verdicts"]] == ["unknown"]
        assert line["verdicts"][0]["reason"] == "No warranty rule for this product yet"
        assert c.get(f"{JOBS}/{empty.id}").json()["warranty"] == []


def test_j8_verdicts_are_computed_at_read_time_nothing_is_stored(env, today):
    from app.models.warranty import WarrantyTerm

    kinds = job_with_policy_kinds(env)
    product, job = make_product(env, *WC), make_job(env)
    with api(env) as c:
        add_line(c, job.id, product.id, kind_id=kinds["exp"].id, purchase_date="2020-03-15")
        assert c.get(f"{JOBS}/{job.id}").json()["warranty"][0]["verdicts"][0]["verdict"] == "expired"
        env.db.query(WarrantyTerm).filter(WarrantyTerm.kind_id == kinds["exp"].id).update({"duration_months": 1200})
        env.db.flush()
        assert c.get(f"{JOBS}/{job.id}").json()["warranty"][0]["verdicts"][0]["verdict"] == "covered"


def test_j8_two_lines_of_one_job_each_get_their_own_verdicts(env, today):
    kinds = job_with_policy_kinds(env)
    product, job = make_product(env, *WC), make_job(env)
    with api(env) as c:
        add_line(c, job.id, product.id, kind_id=kinds["life"].id, purchase_date="2020-03-15")
        add_line(c, job.id, product.id, kind_id=kinds["exp"].id, purchase_date="2020-03-15")
        lines = c.get(f"{JOBS}/{job.id}").json()["warranty"]
    assert [[v["verdict"] for v in l["verdicts"]] for l in lines] == [["covered"], ["expired"]]


# ------------------------------------------------------------------ J9 summary


@pytest.mark.parametrize(
    "kind,purchase,expected",
    [
        ("life", "2020-03-15", "covered"),
        ("mix", "2020-03-15", "partly_covered"),
        ("exp", "2020-03-15", "not_covered"),
        ("none", "2020-03-15", "not_covered"),
        ("life", None, "unknown"),
    ],
)
def test_j9_one_line_summary(env, today, kind, purchase, expected):
    kinds = job_with_policy_kinds(env)
    product, job = make_product(env, *WC), make_job(env)
    body = {"kind_id": kinds[kind].id}
    if purchase:
        body["purchase_date"] = purchase
    with api(env) as c:
        add_line(c, job.id, product.id, **body)
        assert summary_of(c, job) == expected


def test_j9_a_job_without_lines_has_a_null_summary(env, today):
    job = make_job(env)
    with api(env) as c:
        assert summary_of(c, job) is None


def test_j9_the_summary_spans_every_line_of_the_job(env, today):
    kinds = job_with_policy_kinds(env)
    product = make_product(env, *WC)
    cases = {
        "partly": [("life", "2020-03-15"), ("exp", "2020-03-15")],
        "unknown_and_covered": [("life", "2020-03-15"), ("life", None)],
        "unknown_and_expired": [("exp", "2020-03-15"), ("life", None)],
    }
    jobs = {name: make_job(env) for name in cases}
    with api(env) as c:
        for name, lines in cases.items():
            for kind, purchase in lines:
                body = {"kind_id": kinds[kind].id, **({"purchase_date": purchase} if purchase else {})}
                add_line(c, jobs[name].id, product.id, **body)
        assert summary_of(c, jobs["partly"]) == "partly_covered"
        assert summary_of(c, jobs["unknown_and_covered"]) == "partly_covered"
        assert summary_of(c, jobs["unknown_and_expired"]) == "not_covered"


def _five_jobs(env, c):
    kinds = job_with_policy_kinds(env)
    product = make_product(env, *WC)
    tag = f"ZZTSUM{uuid.uuid4().hex[:6]}"
    jobs = {}
    for name in ("not_covered", "covered", "unknown", "none", "partly_covered"):
        jobs[name] = make_job(env, customer_name=f"{tag} {name}")
    for name, (kind, purchase) in {
        "not_covered": ("exp", "2020-03-15"),
        "covered": ("life", "2020-03-15"),
        "unknown": ("life", None),
        "partly_covered": ("mix", "2020-03-15"),
    }.items():
        body = {"kind_id": kinds[kind].id, **({"purchase_date": purchase} if purchase else {})}
        add_line(c, jobs[name].id, product.id, **body)
    return tag, jobs


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_j9_the_list_sorts_on_the_summary_on_the_server_and_the_order_holds_across_pages(env, today, direction):
    with api(env) as c:
        tag, jobs = _five_jobs(env, c)
        order = ["covered", "partly_covered", "not_covered", "unknown", "none"]
        expected = [jobs[n].id for n in (order if direction == "asc" else order[::-1])]
        paged = []
        for page in (1, 2, 3):
            r = c.get(JOBS, params={"query": tag, "sort": "warranty_summary", "dir": direction, "limit": 2, "page": page})
            assert r.status_code == 200, r.text
            paged += [x["id"] for x in r.json()["data"]]
    assert paged == expected


def test_j9_the_list_filters_on_one_or_several_summaries(env, today):
    with api(env) as c:
        tag, jobs = _five_jobs(env, c)

        def got(*values):
            params = [("query", tag), ("limit", 50)] + [("warranty_summary", v) for v in values]
            r = c.get(JOBS, params=params)
            assert r.status_code == 200, r.text
            return r.json()

        assert {x["id"] for x in got("covered")["data"]} == {jobs["covered"].id}
        both = got("covered", "unknown")
        assert {x["id"] for x in both["data"]} == {jobs["covered"].id, jobs["unknown"].id}
        assert both["pagination"]["total"] == 2
        comma = c.get(JOBS, params={"query": tag, "warranty_summary": "not_covered,partly_covered"}).json()
        assert {x["id"] for x in comma["data"]} == {jobs["not_covered"].id, jobs["partly_covered"].id}


# ------------------------------------------------------------------ J10 audit


def test_j10_line_add_edit_and_remove_write_audit_rows_that_belong_to_the_job(env, today):
    product, job = make_product(env, *WC), make_job(env)
    with api(env) as c:
        line_id = add_line(c, job.id, product.id).json()["id"]
        c.patch(f"{lines_url(job.id)}/{line_id}", json={"purchase_date": "2021-01-02"})
        c.delete(f"{lines_url(job.id)}/{line_id}")
    assert [r.action for r in line_audit(env, job.id)] == ["CREATE", "UPDATE", "DELETE"]


# ------------------------------------------------------------------ P3 writes need dispatch


def test_p3_writing_lines_needs_dispatch_and_reading_needs_only_view(env, today):
    from app.models.service_jobs import ServiceJobProduct

    product, job = make_product(env, *WC), make_job(env)
    line = ServiceJobProduct(
        id=str(uuid.uuid4()), service_job_id=job.id, product_id=product.id, company_id=env.company_id
    )
    env.db.add(line)
    env.db.flush()
    with api(env, {VIEW}) as c:
        assert add_line(c, job.id, product.id).status_code == 403
        assert c.patch(f"{lines_url(job.id)}/{line.id}", json={"purchase_date": "2021-01-02"}).status_code == 403
        assert c.delete(f"{lines_url(job.id)}/{line.id}").status_code == 403
        assert c.get(lines_url(job.id)).status_code == 200


# ------------------------------------------------------------------ S3 / E6 no guessed kind


def test_s3_a_category_that_equals_a_kind_name_or_code_still_gets_no_kind(env, today):
    seed_v15(env)
    product = make_product(env, "ZZT-GUESS-1", "water_closet", name="Water Closet")
    job = make_job(env)
    with api(env) as c:
        line = add_line(c, job.id, product.id, purchase_date="2020-03-15").json()
        assert line["kind_id"] is None
        (w,) = c.get(f"{JOBS}/{job.id}").json()["warranty"]
        assert [v["verdict"] for v in w["verdicts"]] == ["unknown"]
        assert w["verdicts"][0]["reason"] == "No warranty rule for this product yet"
        assert summary_of(c, job) == "unknown"
