#!/usr/bin/env python3
"""One-off: make named shipping orders follow AutoCount, without deploying #1411.

WHAT IT DOES (per --spo, inside one company)
--------------------------------------------
When a shipping order (`spo_number`) carries AutoCount lines (`source_ref` set),
AutoCount is the truth for it (owner ruling, 1 Oct 2026). The Excel-era rows
(no `source_ref`, `source_system` NULL or `scm_upload`, no `po_line_id`) are:

1. SUPERSEDED where AutoCount lists the same goods - same product at the same
   warehouse / location, or (no warehouse on the Excel row) the same product
   with exactly equal ordered totals. Their receipt is carried onto the
   AutoCount lines (each line up to its own quantity, the rest on the last,
   never lowering what a line already states), their GRN picks move onto those
   lines (split by capacity, same warehouse first, when the lines sit at
   different locations; an AutoCount GRN line is never split), their order-link
   claims and order-inquiry links move to the first line, and the Excel rows are
   deleted.
2. REMOVED as ORPHANS when AutoCount does not list their product at all - but
   only when received is 0 and no GRN pick, order-link claim or order-inquiry
   link (any company) points at them. Otherwise they are left untouched and
   reported ORPHAN-BLOCKED with the counts. No product substitution is guessed.
3. KEPT, and reported, in every other case: the product is listed but the
   quantities do not reconcile, or the AutoCount lines could not hold the
   receipt the Excel rows already carry ("received locked").

Only the newest AutoCount document version (DocKey) on the number is used; rows
of an older DocKey are reported and never touched.

SAFETY
------
- DRY-RUN unless --apply. The dry run prints exactly what --apply would write.
- One transaction per SPO. Before anything is deleted the script proves, in
  that transaction, that the carry equals what the Excel rows held, that the
  AutoCount lines now state at least that, and that no pick (any company)
  still points at a row about to be deleted. Any failure rolls the SPO back
  and the run moves to the next one (exit code 3).
- Preflight: refuses to run unless every table and column it reads or writes
  exists on the target DB (`stated_received` from migration 488, `retired_at`,
  `scm.order_link_claim`, `projects.order_inquiry_links`, ...).
- Plain SQL through the app's own DATABASE_URL; it imports nothing from the
  app at all, so it runs against whatever code the container holds. Raw SQL
  bypasses the ORM audit listeners, so KEEP THE LOG (tee it): it names every
  row deleted with its quantities, every link moved old -> new and every
  quantity carried.
- It does not recompute the packing lists' stored line statuses. After an
  apply it prints each packing list it touched: open each one once in the
  CRM (Procurement > Packing Lists); the detail page recomputes and saves the
  status the chatbot reads.

RUN IT IN THE PROD BACKEND CONTAINER (docker exec)
--------------------------------------------------
The container already has DATABASE_URL in its environment and the app at /app
(Dockerfile WORKDIR /app; compose service `backend`, container
`sorento_crm_backend` - check `docker ps` for the real name on the host).

    # 1. copy the file in (from a checkout of this branch on the host)
    docker cp sorento_crm_backend/scripts/oneoff/dedupe_spo_standalone.py \
        sorento_crm_backend:/tmp/dedupe_spo_standalone.py

    # 2. DRY RUN (default) - read the plan, keep the log
    docker exec -it -w /app sorento_crm_backend \
        python /tmp/dedupe_spo_standalone.py --company SRT --spo SPO-2026/08-0074 \
        | tee spo-0074-dryrun.log

    # 3. APPLY, only after the dry run has been read and approved
    docker exec -it -w /app sorento_crm_backend \
        python /tmp/dedupe_spo_standalone.py --company SRT --spo SPO-2026/08-0074 --apply \
        | tee spo-0074-apply.log

    # 4. open each packing list the apply printed, once, in the CRM
    # 5. run the dry run again: it must report nothing left to do

`--company` is `companies.code`; Sorento's is `SRT` (seeded by
alembic/versions/302_multi_company_scaffold.py:158). `--spo` is repeatable.
`--database-url` overrides DATABASE_URL (local / dev testing only).

Exit codes: 0 done, 1 bad arguments / unknown company, 2 preflight failed,
3 at least one SPO was refused by a guard (rolled back).
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Column, MetaData, Table, create_engine, func, select, text, update
from sqlalchemy.dialects.postgresql import UUID

XLSX_SOURCE_SYSTEM = "scm_upload"
RECEIVED_STATUSES = ("fully_received", "received")

#: (schema, table) -> columns this script reads or writes.
REQUIRED = {
    ("public", "companies"): ("id", "code"),
    ("public", "spo_allocations"): (
        "id", "company_id", "spo_number", "spo_line_number", "product_id",
        "warehouse_id", "location_code", "allocated_quantity", "quantity_received",
        "quantity_rejected", "stated_received", "retired_at", "receipt_status",
        "line_status", "source_system", "source_ref", "source_doc_ref", "po_line_id",
        "inbound_shipment_id", "storage_zone_id", "uom_id", "allocation_notes",
        "created_at",
    ),
    ("public", "picking_lines"): (
        "id", "picking_header_id", "spo_allocation_id", "product_id", "company_id",
        "quantity_expected", "quantity_picked", "qty_accepted", "source_warehouse_id",
        "destination_warehouse_id", "dtl_key", "uom_id", "picked_condition",
        "condition_remarks", "batch_number_picked", "expiry_date", "unit_cost",
        "spo_number_raw", "po_line_id", "item_code", "location_code", "created_at",
    ),
    ("public", "picking_headers"): ("id", "picking_status"),
    ("scm", "order_link_claim"): ("id", "spo_allocation_id", "company_id"),
    ("projects", "order_inquiry_links"): ("id", "spo_allocation_id", "company_id"),
}


# The two link tables live outside `public`; declared as Core tables (not text)
# so a schema_translate_map, if the connection carries one, applies to them too.
_META = MetaData()
_LINK_TABLES = {
    "claim": Table(
        "order_link_claim", _META,
        Column("id", UUID), Column("spo_allocation_id", UUID), Column("company_id", UUID),
        schema="scm",
    ),
    "order-inquiry link": Table(
        "order_inquiry_links", _META,
        Column("id", UUID), Column("spo_allocation_id", UUID), Column("company_id", UUID),
        schema="projects",
    ),
}


class GuardFailed(RuntimeError):
    """The SPO would lose a receipt; it is rolled back untouched."""


# --------------------------------------------------------------------- preflight
def preflight(db) -> list[str]:
    """Every missing table/column, as readable lines (empty = OK)."""
    missing = []
    for (schema, table), columns in REQUIRED.items():
        present = {
            row[0]
            for row in db.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = :t"
                ),
                {"s": schema, "t": table},
            )
        }
        if not present:
            missing.append(f"table {schema}.{table} is missing")
            continue
        for column in columns:
            if column not in present:
                missing.append(f"column {schema}.{table}.{column} is missing")
    return missing


# ------------------------------------------------------------------- pure rules
def _key(product_id, warehouse_id, location_code):
    product = str(product_id) if product_id else None
    if warehouse_id:
        return (product, f"wh:{warehouse_id}")
    location = (location_code or "").strip().upper()
    return (product, f"loc:{location}" if location else None)


def _match_keys(row) -> list:
    keys = [_key(row["product_id"], row["warehouse_id"], row["location_code"])]
    if row["warehouse_id"]:
        loc = _key(row["product_id"], None, row["location_code"])
        if loc[1] is not None and loc not in keys:
            keys.append(loc)
    return keys


def distribute(total: int, quantities: list[int]) -> list[int]:
    """Each up to its own quantity, any remainder on the LAST (never lost)."""
    remaining = max(int(total or 0), 0)
    shares = []
    for position, quantity in enumerate(quantities):
        take = remaining if position == len(quantities) - 1 else min(remaining, max(int(quantity or 0), 0))
        take = max(take, 0)
        remaining -= take
        shares.append(take)
    return shares


def _i(value) -> int:
    return int(value or 0)


@dataclass
class Group:
    rows: list
    lines: list
    split: bool  # lines at different locations: picks split by capacity


@dataclass
class Plan:
    groups: list = field(default_factory=list)
    kept: list = field(default_factory=list)  # (row, reason)
    orphans: list = field(default_factory=list)


def plan_spo(excel_rows: list, lines: list) -> Plan:
    """The follow-AutoCount plan for one SPO. `lines` = newest DocKey's rows in
    `spo_line_number` order; `excel_rows` = its Excel-era rows."""
    plan = Plan()
    rows = sorted(excel_rows, key=lambda r: (r["spo_line_number"] if r["spo_line_number"] is not None else 10**9, str(r["id"])))
    lines_by_key: dict = {}
    for index, line in enumerate(lines):
        for key in _match_keys(line):
            lines_by_key.setdefault(key, []).append(index)
    rows_by_key: dict = {}
    for row in rows:
        rows_by_key.setdefault(_key(row["product_id"], row["warehouse_id"], row["location_code"]), []).append(row)

    claimed: set = set()
    kept_groups = []
    for key in sorted(rows_by_key, key=lambda k: (0 if (k[1] or "").startswith("wh:") else 1, str(k[0]), str(k[1]))):
        group_rows = rows_by_key[key]
        indexes = [i for i in lines_by_key.get(key, ()) if i not in claimed]
        if not indexes:
            kept_groups.append((key, group_rows))
            continue
        received = sum(_i(r["quantity_received"]) for r in group_rows)
        allocated = sum(_i(r["allocated_quantity"]) for r in group_rows)
        if sum(_i(lines[i]["allocated_quantity"]) for i in indexes) < min(received, allocated):
            plan.kept.extend((r, "received locked (AutoCount lines too small for the receipt)") for r in group_rows)
            claimed.update(indexes)
            continue
        claimed.update(indexes)
        plan.groups.append(Group(group_rows, [lines[i] for i in indexes], split=False))

    listed = {str(line["product_id"]) for line in lines if line["product_id"]}
    fallback: dict = {}
    for key, group_rows in kept_groups:
        if key[0] and not (key[1] or "").startswith("wh:") and key[0] in listed:
            fallback.setdefault(key[0], []).extend(group_rows)
        else:
            for row in group_rows:
                if str(row["product_id"]) not in listed:
                    plan.orphans.append(row)
                else:
                    plan.kept.append((row, "product listed by AutoCount at another warehouse"))
    for product, group_rows in fallback.items():
        indexes = [i for i, line in enumerate(lines) if i not in claimed and str(line["product_id"]) == product]
        rows_total = sum(_i(r["allocated_quantity"]) for r in group_rows)
        lines_total = sum(_i(lines[i]["allocated_quantity"]) for i in indexes)
        if indexes and rows_total == lines_total:
            claimed.update(indexes)
            group_rows.sort(key=lambda r: (r["spo_line_number"] if r["spo_line_number"] is not None else 10**9, str(r["id"])))
            plan.groups.append(Group(group_rows, [lines[i] for i in indexes], split=True))
        else:
            plan.kept.extend(
                (r, f"quantities do not reconcile (Excel {rows_total} vs AutoCount {lines_total})")
                for r in group_rows
            )
    return plan


# ------------------------------------------------------------------------ SQL
_ROW_COLUMNS = ", ".join(REQUIRED[("public", "spo_allocations")])


def _rows(db, company_id: str, spo_number: str) -> list:
    return [
        dict(r._mapping)
        for r in db.execute(
            text(
                f"SELECT {_ROW_COLUMNS} FROM spo_allocations "
                "WHERE company_id = :c AND spo_number = :n ORDER BY spo_line_number, id"
            ),
            {"c": company_id, "n": spo_number},
        )
    ]


def _newest_dockey(refs: list) -> tuple[list, list]:
    by_doc: dict = {}
    for row in refs:
        by_doc.setdefault(str(row["source_doc_ref"] or ""), []).append(row)
    if len(by_doc) <= 1:
        return sorted(refs, key=lambda r: (r["spo_line_number"] or 0, str(r["id"]))), []

    def rank(item):
        doc, rows = item
        created = max((r["created_at"] for r in rows if r["created_at"] is not None), default=datetime.min)
        return (created, max((r["spo_line_number"] or 0) for r in rows), doc)

    newest_doc, newest = max(by_doc.items(), key=rank)
    older = [r for doc, rows in by_doc.items() if doc != newest_doc for r in rows]
    return sorted(newest, key=lambda r: (r["spo_line_number"] or 0, str(r["id"]))), older


def _link_counts(db, allocation_id) -> tuple[int, int, int]:
    """(picks, claims, order-inquiry links) on one allocation, ANY company."""
    picks = _i(db.execute(
        text("SELECT count(*) FROM picking_lines WHERE spo_allocation_id = :a"), {"a": str(allocation_id)}
    ).scalar())
    claims, links = (
        _i(db.execute(
            select(func.count()).select_from(table).where(table.c.spo_allocation_id == str(allocation_id))
        ).scalar())
        for table in _LINK_TABLES.values()
    )
    return picks, claims, links


def _move_picks_whole(db, from_ids, to_id, company_id, write, log) -> int:
    picks = db.execute(
        text(
            "SELECT id, spo_allocation_id, quantity_picked FROM picking_lines "
            "WHERE spo_allocation_id = ANY(CAST(:ids AS uuid[])) AND (company_id = :c OR company_id IS NULL) "
            "ORDER BY created_at, id"
        ),
        {"ids": [str(i) for i in from_ids], "c": company_id},
    ).all()
    for pick in picks:
        log(f"move pick {pick.id} ({_i(pick.quantity_picked)}) {pick.spo_allocation_id} -> {to_id}")
        if write:
            db.execute(text("UPDATE picking_lines SET spo_allocation_id = :t WHERE id = :p"), {"t": str(to_id), "p": pick.id})
    return len(picks)


def _move_picks_by_capacity(db, from_ids, targets: list, company_id, write, log) -> int:
    """Same warehouse first, then any, each line up to allocated less what
    already picks against it (rejected GRNs hold none), overflow on the last.
    A pick carrying `dtl_key` (an AutoCount GRN line) is never split."""
    target_ids = [str(t["id"]) for t in targets]
    already = {
        str(r[0]): _i(r[1])
        for r in db.execute(
            text(
                "SELECT pl.spo_allocation_id, coalesce(sum(pl.quantity_picked), 0) FROM picking_lines pl "
                "JOIN picking_headers ph ON ph.id = pl.picking_header_id "
                "WHERE pl.spo_allocation_id = ANY(CAST(:ids AS uuid[])) AND ph.picking_status <> 'rejected' "
                "AND (pl.company_id = :c OR pl.company_id IS NULL) GROUP BY pl.spo_allocation_id"
            ),
            {"ids": target_ids, "c": company_id},
        )
    }
    pool = [
        {"id": str(t["id"]), "wh": str(t["warehouse_id"]) if t["warehouse_id"] else None,
         "avail": max(0, _i(t["allocated_quantity"]) - already.get(str(t["id"]), 0))}
        for t in targets
    ]
    picks = db.execute(
        text(
            "SELECT * FROM picking_lines WHERE spo_allocation_id = ANY(CAST(:ids AS uuid[])) "
            "AND (company_id = :c OR company_id IS NULL) ORDER BY created_at, id"
        ),
        {"ids": [str(i) for i in from_ids], "c": company_id},
    ).mappings().all()
    for pick in picks:
        qty = _i(pick["quantity_picked"])
        wh = pick["source_warehouse_id"] or pick["destination_warehouse_id"]
        wh = str(wh) if wh else None
        draws, remaining = [], qty
        for same in (True, False):
            for entry in pool:
                if remaining <= 0:
                    break
                if (entry["wh"] == wh) is not same or entry["avail"] <= 0:
                    continue
                take = min(remaining, entry["avail"])
                draws.append([entry["id"], take, entry])
                entry["avail"] -= take
                remaining -= take
        if remaining > 0 or not draws:
            draws.append([target_ids[-1], remaining, None])
        chunks: list = []
        for allocation_id, take, entry in draws:
            if chunks and chunks[-1][0] == allocation_id:
                chunks[-1][1] += take
            else:
                chunks.append([allocation_id, take])
        if pick["dtl_key"] is not None and len(chunks) > 1:
            for allocation_id, take, entry in draws[1:]:
                if entry is not None:
                    entry["avail"] += take
            chunks = [[chunks[0][0], qty]]
        if len(chunks) == 1:
            log(f"move pick {pick['id']} ({qty}) {pick['spo_allocation_id']} -> {chunks[0][0]}")
            if write:
                db.execute(text("UPDATE picking_lines SET spo_allocation_id = :t WHERE id = :p"),
                           {"t": chunks[0][0], "p": pick["id"]})
            continue
        states_expected = _i(pick["quantity_expected"]) > 0
        expected = distribute(_i(pick["quantity_expected"]), [c[1] for c in chunks])
        accepted_left = _i(pick["qty_accepted"]) if pick["qty_accepted"] is not None else None
        for position, (allocation_id, chunk_qty) in enumerate(chunks):
            exp = expected[position] if states_expected else 0
            acc = None
            if accepted_left is not None:
                acc = min(accepted_left, chunk_qty)
                accepted_left -= acc
            if position == 0:
                log(f"split pick {pick['id']} ({qty}): keep {chunk_qty} on {allocation_id} "
                    f"(was {pick['spo_allocation_id']})")
                if write:
                    db.execute(
                        text(
                            "UPDATE picking_lines SET spo_allocation_id = :t, quantity_picked = :q, "
                            "quantity_expected = CASE WHEN :se THEN CAST(:e AS integer) ELSE quantity_expected END, "
                            "qty_accepted = CASE WHEN qty_accepted IS NULL THEN NULL ELSE CAST(:a AS integer) END "
                            "WHERE id = :p"
                        ),
                        {"t": allocation_id, "q": chunk_qty, "se": states_expected, "e": exp, "a": acc, "p": pick["id"]},
                    )
                continue
            new_id = str(uuid.uuid4())
            log(f"split pick {pick['id']}: new pick {new_id} ({chunk_qty}) on {allocation_id}")
            if write:
                db.execute(
                    text(
                        "INSERT INTO picking_lines (id, picking_header_id, product_id, source_warehouse_id, "
                        "destination_warehouse_id, uom_id, picked_condition, condition_remarks, batch_number_picked, "
                        "expiry_date, unit_cost, spo_number_raw, po_line_id, item_code, location_code, company_id, "
                        "spo_allocation_id, quantity_expected, quantity_picked, qty_accepted) "
                        "SELECT :nid, picking_header_id, product_id, source_warehouse_id, destination_warehouse_id, "
                        "uom_id, coalesce(picked_condition, 'good'), condition_remarks, batch_number_picked, expiry_date, "
                        "unit_cost, spo_number_raw, po_line_id, item_code, location_code, company_id, :t, :e, :q, "
                        "CAST(:a AS integer) "
                        "FROM picking_lines WHERE id = :p"
                    ),
                    {"nid": new_id, "t": allocation_id, "e": exp, "q": chunk_qty, "a": acc, "p": pick["id"]},
                )
    return len(picks)


def _move_links(db, from_ids, to_id, company_id, write, log) -> int:
    moved = 0
    ids = [str(i) for i in from_ids]
    for label, table in _LINK_TABLES.items():
        rows = db.execute(
            select(table.c.id, table.c.spo_allocation_id).where(
                table.c.spo_allocation_id.in_(ids),
                (table.c.company_id == company_id) | table.c.company_id.is_(None),
            )
        ).all()
        for row in rows:
            log(f"move {label} {row.id} {row.spo_allocation_id} -> {to_id}")
            if write:
                db.execute(update(table).where(table.c.id == row.id).values(spo_allocation_id=str(to_id)))
        moved += len(rows)
    return moved


def _append_note(existing: Optional[str], note: Optional[str]) -> Optional[str]:
    present = [p.strip() for p in (existing or "").split(";") if p.strip()]
    for fragment in (p.strip() for p in (note or "").split(";") if p.strip()):
        if fragment not in present:
            present.append(fragment)
    return "; ".join(present) or None


# -------------------------------------------------------------------- one SPO
def process_spo(db, company_id: str, spo_number: str, *, write: bool, log) -> dict[str, Any]:
    """Plan (and with `write`, apply) one SPO. Raises GuardFailed before any
    delete when a receipt would be lost; the caller rolls back."""
    stats = {"deleted": 0, "orphans_removed": 0, "orphans_blocked": 0, "kept": 0,
             "links_moved": 0, "carried": 0, "shipments": set()}
    rows = _rows(db, company_id, spo_number)
    refs = [r for r in rows if r["source_ref"]]
    excel = [
        r for r in rows
        if not r["source_ref"] and (r["source_system"] or "") in ("", XLSX_SOURCE_SYSTEM) and not r["po_line_id"]
    ]
    if not refs:
        log("no AutoCount lines on this SPO: nothing to follow, untouched")
        return stats
    lines, older = _newest_dockey(refs)
    for row in older:
        log(f"older DocKey row {row['id']} line {row['spo_line_number']} ({row['source_doc_ref']}): not touched")
    if not excel:
        log("no Excel-era rows: already follows AutoCount")
        return stats

    plan = plan_spo(excel, lines)
    for group in plan.groups:
        removed_received = sum(_i(r["quantity_received"]) for r in group.rows)
        shares = distribute(removed_received, [_i(l["allocated_quantity"]) for l in group.lines])
        shipment = next((r["inbound_shipment_id"] for r in group.rows if r["inbound_shipment_id"]), None)
        zone = next((r["storage_zone_id"] for r in group.rows if r["storage_zone_id"]), None)
        uom = next((r["uom_id"] for r in group.rows if r["uom_id"]), None)
        rejected = sum(_i(r["quantity_rejected"]) for r in group.rows)
        notes = "; ".join((r["allocation_notes"] or "").strip() for r in group.rows if (r["allocation_notes"] or "").strip()) or None
        log(f"group {'product fallback' if group.split else 'same destination'}: "
            f"{len(group.rows)} Excel row(s) -> {len(group.lines)} AutoCount line(s)")
        after_total = 0
        for position, (line, share) in enumerate(zip(group.lines, shares)):
            allocated = _i(line["allocated_quantity"])
            received = max(_i(line["quantity_received"]), share)
            after_total += received
            closed = received >= allocated
            stats["carried"] += share
            log(f"carry {share} -> {line['id']} line {line['spo_line_number']} "
                f"(allocated {allocated}, received {_i(line['quantity_received'])} -> {received})")
            if line["inbound_shipment_id"] or shipment:
                stats["shipments"].add(str(line["inbound_shipment_id"] or shipment))
            if write:
                db.execute(
                    text(
                        "UPDATE spo_allocations SET quantity_received = :r, "
                        "stated_received = CASE WHEN :r > coalesce(stated_received, 0) THEN :r ELSE stated_received END, "
                        "line_status = :ls, receipt_status = :rs, "
                        "inbound_shipment_id = coalesce(inbound_shipment_id, :sh), "
                        "storage_zone_id = coalesce(storage_zone_id, :z), uom_id = coalesce(uom_id, :u) "
                        "WHERE id = :id"
                    ),
                    {"r": received, "ls": "closed" if closed else "open",
                     "rs": "fully_received" if closed else "pending",
                     "sh": shipment, "z": zone, "u": uom, "id": line["id"]},
                )
                if position == 0 and (rejected or notes):
                    db.execute(
                        text(
                            "UPDATE spo_allocations SET quantity_rejected = GREATEST(coalesce(quantity_rejected, 0), :rej), "
                            "allocation_notes = :n WHERE id = :id"
                        ),
                        {"rej": rejected, "n": _append_note(line["allocation_notes"], notes), "id": line["id"]},
                    )
        removed_ids = [r["id"] for r in group.rows]
        first = group.lines[0]["id"]
        if group.split:
            stats["links_moved"] += _move_picks_by_capacity(db, removed_ids, group.lines, company_id, write, log)
        else:
            stats["links_moved"] += _move_picks_whole(db, removed_ids, first, company_id, write, log)
        stats["links_moved"] += _move_links(db, removed_ids, first, company_id, write, log)

        # The guard, in this transaction, before anything is deleted.
        if sum(shares) != removed_received:
            raise GuardFailed(f"carry {sum(shares)} != {removed_received} held")
        if after_total < removed_received:
            raise GuardFailed(f"AutoCount lines would state {after_total} < {removed_received} held")
        if write:
            stranded = _i(db.execute(
                text("SELECT count(*) FROM picking_lines WHERE spo_allocation_id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": [str(i) for i in removed_ids]},
            ).scalar())
            if stranded:
                raise GuardFailed(f"{stranded} pick(s) still on Excel rows (another company's?) - fix by hand first")
        for row in group.rows:
            log(f"delete {row['id']} line {row['spo_line_number']} "
                f"(allocated {_i(row['allocated_quantity'])}, received {_i(row['quantity_received'])})")
            if row["inbound_shipment_id"]:
                stats["shipments"].add(str(row["inbound_shipment_id"]))
            if write:
                db.execute(text("DELETE FROM spo_allocations WHERE id = :id"), {"id": row["id"]})
            stats["deleted"] += 1

    for row in plan.orphans:
        received = _i(row["quantity_received"])
        picks, claims, links = _link_counts(db, row["id"])
        facts = (f"{row['id']} line {row['spo_line_number']} (allocated {_i(row['allocated_quantity'])}, "
                 f"received {received}; picks {picks}, claims {claims}, order-inquiry links {links})")
        if received == 0 and not (picks or claims or links):
            log(f"orphan delete {facts}: no AutoCount line for its product")
            if row["inbound_shipment_id"]:
                stats["shipments"].add(str(row["inbound_shipment_id"]))
            if write:
                db.execute(text("DELETE FROM spo_allocations WHERE id = :id"), {"id": row["id"]})
            stats["orphans_removed"] += 1
        else:
            log(f"ORPHAN-BLOCKED {facts}: left untouched")
            stats["orphans_blocked"] += 1

    for row, reason in plan.kept:
        log(f"keep {row['id']} line {row['spo_line_number']} (allocated {_i(row['allocated_quantity'])}, "
            f"received {_i(row['quantity_received'])}): {reason}")
        stats["kept"] += 1
    return stats


# ------------------------------------------------------------------------ CLI
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company", required=True, help="companies.code (Sorento: SRT)")
    parser.add_argument("--spo", action="append", required=True, metavar="SPO_NUMBER",
                        help="spo_number to repair (repeatable)")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--database-url", default=None, help="override DATABASE_URL (local/dev only)")
    return parser


def run(db, company_code: str, spo_numbers: list[str], *, apply: bool, out=print) -> int:
    """`db` is a SQLAlchemy Session or Connection. Returns the exit code."""
    missing = preflight(db)
    if missing:
        out("PREFLIGHT FAILED - this database lacks what the script needs:")
        for line in missing:
            out(f"  {line}")
        return 2
    company_id = db.execute(text("SELECT id FROM companies WHERE code = :c"), {"c": company_code}).scalar()
    if company_id is None:
        out(f"no company with code {company_code!r}")
        return 1
    company_id = str(company_id)
    out(f"=== {company_code} ({company_id}) {'APPLY' if apply else 'DRY-RUN (no writes)'} ===")
    exit_code = 0
    totals = {"deleted": 0, "orphans_removed": 0, "orphans_blocked": 0, "kept": 0, "links_moved": 0}
    for spo_number in [n.strip() for n in spo_numbers if n and n.strip()]:
        out(f"\n--- {spo_number} ---")
        db.rollback()  # every SPO starts in its own transaction
        try:
            stats = process_spo(db, company_id, spo_number, write=apply,
                                log=lambda line: out(f"  {line}"))
        except GuardFailed as exc:
            db.rollback()
            out(f"  ABORTED, rolled back: {exc}")
            exit_code = 3
            continue
        if apply:
            db.commit()
            for shipment_id in sorted(stats["shipments"]):
                out(f"  packing list to re-open (refreshes its stored status): {shipment_id}")
        else:
            db.rollback()
        for key in totals:
            totals[key] += stats[key]
        out(f"  => Excel rows superseded {stats['deleted']}, orphans removed {stats['orphans_removed']}, "
            f"orphans BLOCKED {stats['orphans_blocked']}, kept {stats['kept']}, "
            f"links moved {stats['links_moved']}, received carried {stats['carried']}, "
            f"PLs touched {len(stats['shipments'])}")
    out(f"\n=== {'APPLIED' if apply else 'DRY-RUN'}: superseded {totals['deleted']}, "
        f"orphans removed {totals['orphans_removed']}, orphans BLOCKED {totals['orphans_blocked']}, "
        f"kept {totals['kept']}, links moved {totals['links_moved']} ===")
    return exit_code


def main() -> int:
    args = build_parser().parse_args()
    url = args.database_url or os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set (the backend container sets it; or pass --database-url)")
        return 1
    engine = create_engine(url)
    with engine.connect() as conn:
        return run(conn, args.company, args.spo, apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
