"""AFTER-SALES-P2 red tests: warranty configuration API (UAC C1-C7, K4).

Wire contract the coder implements (all under /api/v1/after-sales/warranty, acting user has every permission):

* policies   GET list / POST 201 / GET,PATCH,DELETE {id} / POST {id}/supersede (body {version,
             effective_from, policy_text?}; 200 with {"closed": <policy>, "created": <policy>}).
             Row: id, version, effective_from, effective_to, term_count. Sort keys: version,
             effective_from, effective_to. Conflicts 409, bad input 422, other company's id 404.
* terms      GET ?policy_id= (plain list, ordered by part_name), POST (policy_id, kind_id, part_name,
             duration_months, is_lifetime, covered_defect_type_ids, installation_included, qualifications,
             exclusions) 201, PATCH,DELETE {id}. Duplicate (policy, kind, part) 409.
* kinds      GET list (rows carry rule_count, term_count, is_active; sort keys code, name, is_active,
             rule_count, term_count; filters is_active=true|false, has_no_rule=true) / POST / PATCH / DELETE.
             Delete of a used kind: 409 whose message contains "term", "rule" or "job" (the use).
* kind-rules GET list (filter `kind_id`, repeatable; sort keys kind, match_type, match_value, priority) /
             POST / PATCH / DELETE; POST kind-rules/test {product_id} -> 200
             {"resolved_kind": {id, code, name} | null, "deciding_rule": {id, match_type, match_value} | null}.
* audit      entity_type = table name (warranty_policies, warranty_terms, warranty_product_kinds,
             warranty_kind_rules); a term's audit row has root_entity_type warranty_policies / root id the policy.
* lists      {"data": [...], "pagination": {"total", "page", "limit"}}.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from ._warranty_p2_support import (
    KINDS,
    POLICIES,
    RULES,
    TERMS,
    WC,
    api as _api,
    audit_of,
    defect,
    env,  # noqa: F401
    foreign_defect,
    make_company,
    make_kind,
    make_policy,
    make_product,
    make_rule,
    make_term,
    mentions,
)
from ._pg_fixture import unique_code

D = date


def api(env, *args, **kwargs):
    """Configuration writes are admin-only (UAC P1): act as role admin."""
    kwargs.setdefault("roles", {"admin"})
    return _api(env, *args, **kwargs)


def ids(resp):
    assert resp.status_code == 200, resp.text
    return [r["id"] for r in resp.json()["data"]]


def post_policy(client, version, start, end=None, **extra):
    body = {"version": version, "effective_from": start.isoformat(), **extra}
    if end is not None:
        body["effective_to"] = end.isoformat()
    return client.post(POLICIES, json=body)


# ------------------------------------------------------------------ C1 policies


def test_c1_create_a_policy_returns_201_with_its_window(env):
    with api(env) as c:
        r = post_policy(c, "ZV1", D(2026, 1, 1), D(2026, 12, 31))
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["version"], body["effective_from"], body["effective_to"]) == ("ZV1", "2026-01-01", "2026-12-31")


def test_c1_the_same_version_twice_in_a_company_is_409(env):
    with api(env) as c:
        assert post_policy(c, "ZDUP", D(2020, 1, 1), D(2020, 12, 31)).status_code == 201
        assert post_policy(c, "ZDUP", D(2022, 1, 1), D(2022, 12, 31)).status_code == 409


def test_c1_overlapping_windows_are_409_and_the_message_names_the_other_version_and_dates(env):
    make_policy(env, "ZOTHER", D(2024, 1, 1), D(2024, 12, 31))
    with api(env) as c:
        r = post_policy(c, "ZNEW", D(2024, 12, 31), D(2025, 6, 30))
    assert r.status_code == 409
    assert "ZOTHER" in r.text
    assert mentions(r.text, D(2024, 1, 1)) and mentions(r.text, D(2024, 12, 31))


def test_c1_windows_that_only_touch_end_to_start_are_allowed(env):
    make_policy(env, "ZA", D(2024, 1, 1), D(2024, 12, 31))
    with api(env) as c:
        assert post_policy(c, "ZB", D(2025, 1, 1), D(2025, 12, 31)).status_code == 201


def test_c1_an_open_ended_policy_overlaps_everything_after_its_start(env):
    make_policy(env, "ZOPEN", D(2024, 1, 1), None)
    with api(env) as c:
        assert post_policy(c, "ZLATE", D(2031, 1, 1), D(2031, 12, 31)).status_code == 409
        assert post_policy(c, "ZEARLY", D(2023, 1, 1), D(2023, 12, 31)).status_code == 201


def test_c1_another_companys_policy_never_overlaps_ours(env):
    make_policy(env, "ZTHEIRS", D(2024, 1, 1), None, company_id=make_company(env))
    with api(env) as c:
        assert post_policy(c, "ZOURS", D(2024, 6, 1), D(2024, 12, 31)).status_code == 201


def test_c1_editing_into_an_overlap_is_409_but_a_policy_does_not_overlap_itself(env):
    a = make_policy(env, "ZE1", D(2020, 1, 1), D(2020, 12, 31))
    b = make_policy(env, "ZE2", D(2021, 1, 1), D(2021, 12, 31))
    with api(env) as c:
        assert c.patch(f"{POLICIES}/{b.id}", json={"effective_from": "2020-06-01"}).status_code == 409
        assert c.patch(f"{POLICIES}/{a.id}", json={"effective_to": "2020-11-30"}).status_code == 200


def test_c1_effective_to_before_effective_from_is_422_on_create_and_patch(env):
    a = make_policy(env, "ZINV", D(2020, 1, 1), D(2020, 12, 31))
    with api(env) as c:
        assert post_policy(c, "ZBAD", D(2024, 5, 1), D(2024, 4, 30)).status_code == 422
        assert c.patch(f"{POLICIES}/{a.id}", json={"effective_to": "2019-12-31"}).status_code == 422


def test_c1_delete_a_policy_removes_its_terms(env):
    from app.models.warranty import WarrantyTerm

    policy, kind = make_policy(env, "ZDEL"), make_kind(env)
    make_term(env, policy, kind, "Body", months=12)
    with api(env) as c:
        assert c.delete(f"{POLICIES}/{policy.id}").status_code == 200
        assert c.get(f"{POLICIES}/{policy.id}").status_code == 404
    env.db.expire_all()
    assert env.db.query(WarrantyTerm).filter(WarrantyTerm.policy_id == policy.id).count() == 0


def test_c1_another_companys_policy_is_404_on_get_patch_delete(env):
    theirs = make_policy(env, "ZHIDE", D(2020, 1, 1), None, company_id=make_company(env))
    with api(env) as c:
        assert c.get(f"{POLICIES}/{theirs.id}").status_code == 404
        assert c.patch(f"{POLICIES}/{theirs.id}", json={"policy_text": "x"}).status_code == 404
        assert c.delete(f"{POLICIES}/{theirs.id}").status_code == 404


# ------------------------------------------------------------------ C2 supersede


def test_c2_supersede_closes_the_old_day_before_and_creates_the_new_one(env):
    old = make_policy(env, "ZOLD", D(2000, 1, 1), None)
    with api(env) as c:
        r = c.post(f"{POLICIES}/{old.id}/supersede", json={"version": "ZNEW", "effective_from": "2026-12-01"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["closed"]["version"], body["closed"]["effective_to"]) == ("ZOLD", "2026-11-30")
        assert (body["created"]["version"], body["created"]["effective_from"], body["created"]["effective_to"]) == (
            "ZNEW", "2026-12-01", None,
        )
        assert c.get(f"{POLICIES}/{old.id}").json()["effective_to"] == "2026-11-30"


@pytest.mark.parametrize("start", ["2000-01-01", "1999-06-01"])
def test_c2_a_start_on_or_before_the_old_start_is_422_and_nothing_changes(env, start):
    old = make_policy(env, "ZOLD2", D(2000, 1, 1), None)
    with api(env) as c:
        r = c.post(f"{POLICIES}/{old.id}/supersede", json={"version": "ZN2", "effective_from": start})
        assert r.status_code == 422
        assert c.get(f"{POLICIES}/{old.id}").json()["effective_to"] is None


def test_c2_a_closed_policy_cannot_be_superseded(env):
    closed = make_policy(env, "ZCLOSED", D(2000, 1, 1), D(2010, 12, 31))
    with api(env) as c:
        assert c.post(f"{POLICIES}/{closed.id}/supersede", json={"version": "ZX", "effective_from": "2011-01-01"}).status_code == 409


def test_c2_a_failed_supersede_leaves_the_old_policy_open_and_creates_nothing(env):
    old = make_policy(env, "ZOLD3", D(2000, 1, 1), None)
    make_policy(env, "ZTAKEN", D(1990, 1, 1), D(1999, 12, 31))
    with api(env) as c:
        r = c.post(f"{POLICIES}/{old.id}/supersede", json={"version": "ZTAKEN", "effective_from": "2026-12-01"})
        assert r.status_code == 409
        assert c.get(f"{POLICIES}/{old.id}").json()["effective_to"] is None
        assert c.post(f"{POLICIES}/{old.id}/supersede", json={"version": "  ", "effective_from": "2026-12-01"}).status_code == 422
        assert c.get(f"{POLICIES}/{old.id}").json()["effective_to"] is None


# ------------------------------------------------------------------ C3 terms


def make_term_body(policy, kind, **over):
    return {"policy_id": policy.id, "kind_id": kind.id, "part_name": "Body", "duration_months": 24, **over}


def test_c3_a_term_with_months_and_a_lifetime_term_are_both_accepted(env):
    policy, kind = make_policy(env), make_kind(env)
    with api(env) as c:
        r1 = c.post(TERMS, json=make_term_body(policy, kind, part_name="Seat", installation_included=True))
        r2 = c.post(TERMS, json=make_term_body(policy, kind, part_name="Body", duration_months=None, is_lifetime=True))
    assert r1.status_code == 201 and r1.json()["duration_months"] == 24 and r1.json()["installation_included"] is True
    assert r2.status_code == 201 and r2.json()["is_lifetime"] is True


@pytest.mark.parametrize(
    "over",
    [
        {"is_lifetime": True, "duration_months": 12},
        {"is_lifetime": False, "duration_months": None},
        {"duration_months": 0},
        {"duration_months": -3},
    ],
)
def test_c3_lifetime_xor_months_is_422_on_create(env, over):
    policy, kind = make_policy(env), make_kind(env)
    with api(env) as c:
        assert c.post(TERMS, json=make_term_body(policy, kind, **over)).status_code == 422


def test_c3_editing_a_term_into_both_or_neither_is_422(env):
    policy, kind = make_policy(env), make_kind(env)
    term = make_term(env, policy, kind, "Body", months=12)
    with api(env) as c:
        assert c.patch(f"{TERMS}/{term.id}", json={"is_lifetime": True}).status_code == 422
        assert c.patch(f"{TERMS}/{term.id}", json={"duration_months": None}).status_code == 422
        assert c.patch(f"{TERMS}/{term.id}", json={"is_lifetime": True, "duration_months": None}).status_code == 200


def test_c3_defect_ids_must_belong_to_the_defect_type_set(env):
    policy, kind = make_policy(env), make_kind(env)
    good = defect(env, "Leakage")
    with api(env) as c:
        ok = c.post(TERMS, json=make_term_body(policy, kind, covered_defect_type_ids=[good]))
        assert ok.status_code == 201 and ok.json()["covered_defect_type_ids"] == [good]
        other = make_kind(env)
        for bad in (str(uuid.uuid4()), foreign_defect(env)):
            r = c.post(TERMS, json=make_term_body(policy, other, covered_defect_type_ids=[good, bad]))
            assert r.status_code == 422, r.text


def test_c3_the_same_part_of_the_same_kind_twice_in_a_policy_is_409(env):
    policy, kind = make_policy(env), make_kind(env)
    with api(env) as c:
        assert c.post(TERMS, json=make_term_body(policy, kind)).status_code == 201
        assert c.post(TERMS, json=make_term_body(policy, kind)).status_code == 409


def test_c3_terms_of_another_companys_policy_are_404(env):
    theirs = make_policy(env, "ZTH", D(2020, 1, 1), None, company_id=make_company(env))
    kind = make_kind(env)
    with api(env) as c:
        assert c.post(TERMS, json=make_term_body(theirs, kind)).status_code == 404
        assert c.get(TERMS, params={"policy_id": theirs.id}).status_code == 404


def test_c3_terms_list_for_a_policy_is_ordered_by_part_and_delete_works(env):
    policy, kind = make_policy(env), make_kind(env)
    for part in ("Seat", "Body", "Fittings"):
        make_term(env, policy, kind, part, months=12)
    with api(env) as c:
        rows = c.get(TERMS, params={"policy_id": policy.id}).json()
        assert [r["part_name"] for r in rows] == ["Body", "Fittings", "Seat"]
        assert c.delete(f"{TERMS}/{rows[0]['id']}").status_code == 200
        assert len(c.get(TERMS, params={"policy_id": policy.id}).json()) == 2


# ------------------------------------------------------------------ C4 kinds


def test_c4_kind_code_is_unique_409(env):
    with api(env) as c:
        assert c.post(KINDS, json={"code": "zdup_kind", "name": "ZZT A"}).status_code == 201
        assert c.post(KINDS, json={"code": "zdup_kind", "name": "ZZT B"}).status_code == 409


def test_c4_a_kind_used_by_a_term_cannot_be_deleted_and_the_message_names_the_use(env):
    policy, kind = make_policy(env), make_kind(env)
    make_term(env, policy, kind, "Body", months=12)
    with api(env) as c:
        r = c.delete(f"{KINDS}/{kind.id}")
    assert r.status_code == 409
    assert "term" in r.text.lower()


def test_c4_a_kind_used_by_a_rule_cannot_be_deleted(env):
    kind = make_kind(env)
    make_rule(env, kind, "category", "SRT-WC")
    with api(env) as c:
        r = c.delete(f"{KINDS}/{kind.id}")
    assert r.status_code == 409
    assert "rule" in r.text.lower()


def test_c4_a_kind_used_by_a_job_line_cannot_be_deleted(env):
    from app.models.service_jobs import ServiceJobProduct

    kind = make_kind(env)
    product = make_product(env, *WC)
    job = _job(env)
    env.db.add(ServiceJobProduct(id=str(uuid.uuid4()), service_job_id=job.id, product_id=product.id, kind_id=kind.id, company_id=env.company_id))
    env.db.flush()
    with api(env) as c:
        r = c.delete(f"{KINDS}/{kind.id}")
    assert r.status_code == 409
    assert "job" in r.text.lower()


def test_c4_an_unused_kind_deletes_and_a_used_one_can_be_archived_and_restored(env):
    free, used = make_kind(env), make_kind(env)
    make_term(env, make_policy(env), used, "Body", months=12)
    with api(env) as c:
        assert c.delete(f"{KINDS}/{free.id}").status_code == 200
        assert c.patch(f"{KINDS}/{used.id}", json={"is_active": False}).json()["is_active"] is False
        assert c.patch(f"{KINDS}/{used.id}", json={"is_active": True}).json()["is_active"] is True


def _job(env):
    from ._warranty_p2_support import make_job

    return make_job(env)


# ------------------------------------------------------------------ C5 rules / K4 tester


@pytest.mark.parametrize("match_type", ["series", "model_list", "category", "code_prefix"])
def test_c5_every_declared_match_type_can_be_saved(env, match_type):
    kind = make_kind(env)
    with api(env) as c:
        r = c.post(RULES, json={"kind_id": kind.id, "match_type": match_type, "match_value": "ABC", "priority": 2})
    assert r.status_code == 201, r.text
    assert (r.json()["match_type"], r.json()["priority"]) == (match_type, 2)


@pytest.mark.parametrize("match_type,value", [("model_prefix", "ABC"), ("regex", "A.*"), ("", "ABC"), ("category", ""), ("category", "   ")])
def test_c5_an_unknown_match_type_or_blank_value_is_422(env, match_type, value):
    kind = make_kind(env)
    with api(env) as c:
        assert c.post(RULES, json={"kind_id": kind.id, "match_type": match_type, "match_value": value}).status_code == 422


def test_c5_edit_and_delete_a_rule_and_edit_cannot_blank_it(env):
    rule = make_rule(env, make_kind(env), "category", "SRT-WC")
    with api(env) as c:
        assert c.patch(f"{RULES}/{rule.id}", json={"match_value": "SRT-BA"}).json()["match_value"] == "SRT-BA"
        assert c.patch(f"{RULES}/{rule.id}", json={"match_type": "nonsense"}).status_code == 422
        assert c.patch(f"{RULES}/{rule.id}", json={"match_value": " "}).status_code == 422
        assert c.delete(f"{RULES}/{rule.id}").status_code == 200
        assert c.delete(f"{RULES}/{rule.id}").status_code == 404


def test_k4_the_tester_returns_the_winning_kind_and_the_deciding_rule(env):
    tag = unique_code("k4", alpha=True)
    broad, narrow = make_kind(env, f"{tag}-a"), make_kind(env, f"{tag}-z")
    make_rule(env, broad, "category", WC[1])
    decider = make_rule(env, narrow, "code_prefix", "SRTWC")
    product = make_product(env, *WC)
    with api(env) as c:
        r = c.post(f"{RULES}/test", json={"product_id": product.id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resolved_kind"]["id"] == narrow.id and body["resolved_kind"]["code"] == narrow.code
    assert body["deciding_rule"]["id"] == decider.id and body["deciding_rule"]["match_type"] == "code_prefix"


def test_k4_a_product_no_rule_reaches_returns_none_not_an_error(env):
    product = make_product(env, "CB110", "CB-FT")
    with api(env) as c:
        r = c.post(f"{RULES}/test", json={"product_id": product.id})
        assert r.status_code == 200
        assert r.json()["resolved_kind"] is None and r.json()["deciding_rule"] is None
        assert c.post(f"{RULES}/test", json={}).status_code == 422


# ------------------------------------------------------------------ C6 lists


def test_c6_policies_list_is_paginated_sorted_and_searchable(env):
    tag = unique_code("pl", alpha=True)
    for i, v in enumerate(["c", "a", "b", "e", "d"]):
        make_policy(env, f"{tag}-{v}", D(2000 + i * 2, 1, 1), D(2000 + i * 2, 12, 31))
    with api(env) as c:
        base = {"query": tag, "limit": 2}
        asc = [ids(c.get(POLICIES, params={**base, "sort": "version", "dir": "asc", "page": p})) for p in (1, 2, 3)]
        r = c.get(POLICIES, params={**base, "sort": "version", "dir": "asc"})
        assert r.json()["pagination"] == {"total": 5, "page": 1, "limit": 2}
        flat = [i for page in asc for i in page]
        assert len(flat) == 5 == len(set(flat))
        names = [x["version"] for x in c.get(POLICIES, params={"query": tag, "limit": 50, "sort": "version", "dir": "asc"}).json()["data"]]
        assert names == sorted(names)
        desc = [x["version"] for x in c.get(POLICIES, params={"query": tag, "limit": 50, "sort": "effective_from", "dir": "desc"}).json()["data"]]
        assert desc == [f"{tag}-d", f"{tag}-e", f"{tag}-b", f"{tag}-a", f"{tag}-c"]
        assert [x["version"] for x in c.get(POLICIES, params={"query": f"{tag}-b"}).json()["data"]] == [f"{tag}-b"]


def test_c6_policies_list_never_carries_another_companys_rows(env):
    mine = make_policy(env, "ZMINE")
    theirs = make_policy(env, "ZNOTMINE", D(2001, 1, 1), None, company_id=make_company(env))
    with api(env) as c:
        got = ids(c.get(POLICIES, params={"limit": 200}))
    assert mine.id in got and theirs.id not in got


def test_c6_kinds_list_rows_carry_rule_and_term_counts(env):
    tag = unique_code("kc", alpha=True)
    k = make_kind(env, f"{tag}-a")
    policy = make_policy(env)
    make_term(env, policy, k, "A", months=12)
    make_term(env, policy, k, "B", months=24)
    make_rule(env, k, "category", "SRT-WC")
    make_rule(env, k, "category", "SRT-BA")
    make_rule(env, k, "category", "CB-FT")
    with api(env) as c:
        row = c.get(KINDS, params={"query": tag}).json()["data"][0]
    assert (row["rule_count"], row["term_count"], row["is_active"]) == (3, 2, True)


def test_c6_kinds_sort_on_every_shown_column_and_paginate(env):
    tag = unique_code("ks", alpha=True)
    policy = make_policy(env)
    kinds = [make_kind(env, f"{tag}-{x}", f"{tag} Name {x}") for x in "cabde"]
    for n, k in enumerate(sorted(kinds, key=lambda k: k.code)):
        for i in range(n):
            make_term(env, policy, k, f"P{i}", months=12)
            make_rule(env, k, "series", f"s{n}{i}")
    with api(env) as c:
        for key in ("code", "name", "rule_count", "term_count"):
            for direction in ("asc", "desc"):
                rows = c.get(KINDS, params={"query": tag, "sort": key, "dir": direction, "limit": 50}).json()["data"]
                values = [r[key] for r in rows]
                assert values == sorted(values, reverse=direction == "desc"), (key, direction)
        pages = [ids(c.get(KINDS, params={"query": tag, "sort": "code", "limit": 2, "page": p})) for p in (1, 2, 3)]
        assert [len(p) for p in pages] == [2, 2, 1]


def test_c6_kinds_filter_by_active_and_by_has_no_rule(env):
    tag = unique_code("kf", alpha=True)
    ruled = make_kind(env, f"{tag}-r")
    make_rule(env, ruled, "category", "SRT-WC")
    bare = make_kind(env, f"{tag}-b")
    off = make_kind(env, f"{tag}-o", active=False)
    with api(env) as c:
        base = {"query": tag, "limit": 50}
        assert set(ids(c.get(KINDS, params={**base, "is_active": "false"}))) == {off.id}
        assert set(ids(c.get(KINDS, params={**base, "is_active": "true"}))) == {ruled.id, bare.id}
        assert set(ids(c.get(KINDS, params={**base, "has_no_rule": "true"}))) == {bare.id, off.id}


def test_c6_rules_filter_by_kind_multi_select_sort_and_paginate(env):
    k1, k2, k3 = make_kind(env), make_kind(env), make_kind(env)
    r1 = make_rule(env, k1, "category", "A1", priority=3)
    r2 = make_rule(env, k2, "series", "B2", priority=1)
    r3 = make_rule(env, k3, "code_prefix", "C3", priority=2)
    with api(env) as c:
        both = ids(c.get(RULES, params=[("kind_id", k1.id), ("kind_id", k2.id), ("limit", 50)]))
        assert set(both) == {r1.id, r2.id}
        comma = ids(c.get(RULES, params={"kind_id": f"{k1.id},{k3.id}", "limit": 50}))
        assert set(comma) == {r1.id, r3.id}
        by_priority = ids(c.get(RULES, params=[("kind_id", k1.id), ("kind_id", k2.id), ("kind_id", k3.id), ("sort", "priority"), ("dir", "desc")]))
        assert by_priority == [r1.id, r3.id, r2.id]
        page2 = c.get(RULES, params=[("kind_id", k1.id), ("kind_id", k2.id), ("kind_id", k3.id), ("sort", "priority"), ("dir", "asc"), ("limit", 2), ("page", 2)]).json()
        assert [r["id"] for r in page2["data"]] == [r1.id] and page2["pagination"]["total"] == 3


# ------------------------------------------------------------------ C7 audit


def test_c7_policy_create_edit_delete_write_audit_rows(env):
    with api(env) as c:
        pid = post_policy(c, "ZAUD", D(2030, 1, 1), D(2030, 6, 30)).json()["id"]
        c.patch(f"{POLICIES}/{pid}", json={"policy_text": "edited"})
        c.delete(f"{POLICIES}/{pid}")
    assert [r.action for r in audit_of(env, "warranty_policies", pid)] == ["CREATE", "UPDATE", "DELETE"]


def test_c7_supersede_writes_audit_rows_on_both_policies(env):
    old = make_policy(env, "ZAUDOLD", D(2000, 1, 1), None)
    with api(env) as c:
        body = c.post(f"{POLICIES}/{old.id}/supersede", json={"version": "ZAUDNEW", "effective_from": "2026-12-01"}).json()
    assert "UPDATE" in [r.action for r in audit_of(env, "warranty_policies", old.id)]
    assert "CREATE" in [r.action for r in audit_of(env, "warranty_policies", body["created"]["id"])]


def test_c7_kind_create_archive_and_delete_are_audited(env):
    with api(env) as c:
        kid = c.post(KINDS, json={"code": unique_code("zaud")[:60], "name": "ZZT audit"}).json()["id"]
        c.patch(f"{KINDS}/{kid}", json={"is_active": False})
        c.delete(f"{KINDS}/{kid}")
    rows = audit_of(env, "warranty_product_kinds", kid)
    assert [r.action for r in rows] == ["CREATE", "UPDATE", "DELETE"]
    assert (rows[1].new_values or {}).get("is_active") is False


def test_c7_rule_create_edit_delete_are_audited(env):
    kind = make_kind(env)
    with api(env) as c:
        rid = c.post(RULES, json={"kind_id": kind.id, "match_type": "category", "match_value": "X1"}).json()["id"]
        c.patch(f"{RULES}/{rid}", json={"match_value": "X2"})
        c.delete(f"{RULES}/{rid}")
    assert [r.action for r in audit_of(env, "warranty_kind_rules", rid)] == ["CREATE", "UPDATE", "DELETE"]


def test_c7_a_term_change_is_audited_and_shows_on_its_policys_history(env):
    policy, kind = make_policy(env), make_kind(env)
    with api(env) as c:
        tid = c.post(TERMS, json=make_term_body(policy, kind)).json()["id"]
        c.patch(f"{TERMS}/{tid}", json={"duration_months": 36})
        c.delete(f"{TERMS}/{tid}")
    rows = audit_of(env, "warranty_terms", tid)
    assert [r.action for r in rows] == ["CREATE", "UPDATE", "DELETE"]
    assert all(r.root_entity_type == "warranty_policies" and r.root_entity_id == policy.id for r in rows)
