"""What the supplier calls a product, and what we call it (R16, F11).

Suppliers do not write our codes. Measured on the uploaded JINBAICHUAN stock list, 79 codes
bound to nothing on an exact match, and the reasons are four:

  * the separators are theirs (`SRTWC8357RL` for our `SRTWC8357-RL`);
  * the tokens come in another order (`SRTWC8357-RL-300` for `SRTWC8357-300-RL`) - 4 of them;
  * a trap size is spelled out that our code omits because it is the default
    (`SRTWC8357-RL-250` for `SRTWC8357-RL`, whose description reads `S-TRAP 250MM`);
  * a suffix is glued on after it (`SRTWC286-SH-250UF`, `...-250NEW`).

A LADDER, first unique hit wins, and an ambiguous rung binds NOTHING:

  0. an alias somebody already recorded for THIS supplier;
  1. exact `product_code`;
  2. separator-normalised equality (`entity_resolver._norm_sql`, the expression migration 410
     indexes - shared rather than re-spelled, because two spellings of one rule drift);
  3. token-set reorder - the same tokens, any order;
  4. the trap size dropped, and ONLY where the base product's own description carries that
     size. Without that question the rung finds 28 and 16 of them are wrong: `CWC7606-SH-180`
     is not `CWC7606-SH`, which is the 250. Silence counts as a no.

Ambiguity is not a bind. Two products answering one code cannot both be what the supplier
meant, and picking one puts a container's stock against the wrong item where nothing on
screen disagrees. Two products means two CODES, though: our companies hold the same
catalogue under the same codes, so one spelling seen once per company is one product
wearing one name and is not an ambiguity at all (`_one_per_code`).

Every worked-out bind (rungs 2-4) is WRITTEN DOWN as an `auto` alias with the rung that
found it, so the next upload reads a decision instead of re-deriving a guess, the screen can
show it as a guess, and a human can correct it once. An exact match is not written: the
codes already agree, and a row saying so is a row to maintain for nothing.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.scm import SupplierProductCodeAlias
from app.services.entity_resolver import _norm_sql

#: A token shorter than this is not a stem - it appears in half the catalogue, and probing
#: on it would pull back a candidate set that is no candidate set at all.
_TOKEN_MIN = 4

#: What counts as a trap size. Below 100 and above 499 the number is part of the model
#: (`SRTWB890-600` is a 600mm basin, not a 600mm trap), so it is never dropped.
_SIZE_MIN = 100
_SIZE_MAX = 499

_RUNG_ALIAS = "alias"
_RUNG_EXACT = "exact"
_RUNG_SEPARATOR = "separator"
_RUNG_TOKEN_SET = "token_set"
_RUNG_SIZE_DROP = "size_drop"

#: The rungs whose answer is a DERIVATION rather than an agreement, so it is remembered.
_REMEMBERED = (_RUNG_SEPARATOR, _RUNG_TOKEN_SET, _RUNG_SIZE_DROP)


@dataclass(frozen=True)
class Match:
    """One bound code: which product, and which rung found it."""

    product_id: str
    rung: str


def _norm(value: str) -> str:
    """The Python twin of `_norm_sql`: strip separators and case, keep the rest."""
    return re.sub(r"[-\s]+", "", (value or "")).lower()


def _tokens(value: str) -> list[str]:
    return [t for t in re.split(r"[-\s]+", (value or "").strip()) if t]


def _size_of(token: str) -> Optional[int]:
    """The trap size a token states, or None. `250` yes; `250UF` no - a glued suffix means
    the supplier added a size AND something else, and only a human can say what."""
    if not token.isdigit() or len(token) != 3:
        return None
    size = int(token)
    return size if _SIZE_MIN <= size <= _SIZE_MAX else None


def _supplier_company(db: Session, supplier_id: str) -> Optional[str]:
    """Which company this supplier belongs to, or nothing.

    Read for one reason: when a caller may see several companies, it says which of the
    identical catalogue rows is the one to bind (see `_one_per_code`).
    """
    from app.models.procurement import Supplier

    row = (
        db.query(Supplier.company_id).filter(Supplier.id == str(supplier_id)).first()
    )
    return str(row[0]) if row and row[0] else None


def _one_per_code(rows: list[Product], home: Optional[str]) -> list[Product]:
    """One row per code SPELLING, because a code spelled once per company is one product.

    Companies hold the same catalogue: on the dev copy 11,390 of our codes exist once for
    Sorento and once for Mocha, so a caller granted both - a superadmin, which is who
    uploads a stock list - reads every code twice. Counting that as two products makes every
    rung ambiguous and the ladder answers nothing at all, the exact rung included.

    The supplier's own company decides which row is bound: the stock rows, the invoice
    lines and the alias about to be written all belong to it, so a product from anywhere
    else would file the memory where the people reading it cannot see it. Anything still
    tied is settled on the id, so two runs never disagree.
    """
    best: dict[str, Product] = {}
    for row in sorted(rows, key=lambda r: (str(r.company_id) != home, str(r.id))):
        best.setdefault((row.product_code or "").strip().upper(), row)
    return list(best.values())


def _candidates(
    db: Session, codes: Iterable[str], *, home: Optional[str] = None
) -> list[Product]:
    """Every product sharing a real token with one of these codes - one query per upload.

    Scoped through the ORM, so the company filter applies without restating it: product
    codes are not unique across companies, and an unscoped probe would offer another
    company's catalogue as an answer.
    """
    from sqlalchemy import func, or_

    from app.services.entity_resolver import _ws_insensitive_lower

    patterns: set[str] = set()
    #: The same probe with the separators taken out, because a supplier who writes no
    #: separators at all (`SRTWC8357RL`) shares no TOKEN with `SRTWC8357-RL` - and rung 2
    #: exists for exactly that spelling, so a probe that cannot see it makes the rung dead.
    norm_patterns: set[str] = set()
    for code in codes:
        for token in _tokens(code):
            if len(token) >= _TOKEN_MIN:
                patterns.add(f"%{token.upper()}%")
                norm_patterns.add(f"%{_norm(token)}%")
        whole = _norm(code)
        if len(whole) >= _TOKEN_MIN:
            norm_patterns.add(f"%{whole}%")
    if not patterns and not norm_patterns:
        return []

    normalised = _ws_insensitive_lower(Product.product_code)
    clauses = [func.upper(Product.product_code).like(p) for p in patterns]
    clauses += [normalised.like(p) for p in norm_patterns]
    return _one_per_code(db.query(Product).filter(or_(*clauses)).all(), home)


def _only(ids: set[str]) -> Optional[str]:
    """The one answer, or nothing. Two answers to one code is not an answer."""
    return next(iter(ids)) if len(ids) == 1 else None


def resolve(
    db: Session,
    supplier_id: str,
    codes: Iterable[str],
    *,
    remember: bool = True,
    actor: Optional[str] = None,
) -> dict[str, Match]:
    """Bind each supplier code to one of our products, or leave it out.

    Keyed by the code EXACTLY as it was given - the caller holds rows under that spelling,
    and handing back a tidied version would make the answer unusable.

    `remember=False` is for a caller that only wants to look (a preview): it walks the same
    ladder and writes nothing.
    """
    wanted = [c for c in dict.fromkeys(codes) if (c or "").strip()]
    if not wanted:
        return {}

    out: dict[str, Match] = {}

    # -- rung 0: what somebody already decided ---------------------------------------
    aliases = {
        str(row.supplier_code).strip().upper(): str(row.product_id)
        for row in db.query(SupplierProductCodeAlias)
        .filter(
            SupplierProductCodeAlias.supplier_id == str(supplier_id),
            SupplierProductCodeAlias.supplier_code.isnot(None),
        )
        .all()
    }
    unresolved: list[str] = []
    for code in wanted:
        product_id = aliases.get(code.strip().upper())
        if product_id:
            out[code] = Match(product_id, _RUNG_ALIAS)
        else:
            unresolved.append(code)
    if not unresolved:
        return out

    candidates = _candidates(db, unresolved, home=_supplier_company(db, supplier_id))
    by_exact: dict[str, set[str]] = {}
    by_norm: dict[str, set[str]] = {}
    by_tokens: dict[tuple[str, ...], set[str]] = {}
    described: dict[str, Optional[str]] = {}
    for product in candidates:
        pid = str(product.id)
        code = (product.product_code or "").strip()
        described[pid] = product.description
        by_exact.setdefault(code.upper(), set()).add(pid)
        by_norm.setdefault(_norm(code), set()).add(pid)
        by_tokens.setdefault(
            tuple(sorted(t.upper() for t in _tokens(code))), set()
        ).add(pid)

    written: list[tuple[str, str, str]] = []
    for code in unresolved:
        trimmed = code.strip()
        tokens = [t.upper() for t in _tokens(trimmed)]

        # -- rung 1: exact -----------------------------------------------------------
        hit = _only(by_exact.get(trimmed.upper(), set()))
        if hit:
            out[code] = Match(hit, _RUNG_EXACT)
            continue
        if by_exact.get(trimmed.upper()):
            continue  # two products carry this very code: not ours to choose between

        # -- rung 2: their separators, not ours ---------------------------------------
        pool = by_norm.get(_norm(trimmed), set())
        if pool:
            hit = _only(pool)
            if hit:
                out[code] = Match(hit, _RUNG_SEPARATOR)
                written.append((code, hit, _RUNG_SEPARATOR))
            continue

        # -- rung 3: the same tokens, another order -----------------------------------
        pool = by_tokens.get(tuple(sorted(tokens)), set())
        if pool:
            hit = _only(pool)
            if hit:
                out[code] = Match(hit, _RUNG_TOKEN_SET)
                written.append((code, hit, _RUNG_TOKEN_SET))
            continue

        # -- rung 4: the trap size ours omits, if the product says it is that size ----
        if not tokens:
            continue
        size = _size_of(tokens[-1])
        if size is None:
            continue
        pool = by_tokens.get(tuple(sorted(tokens[:-1])), set())
        confirmed = {
            pid
            for pid in pool
            if f"{size}MM" in (described.get(pid) or "").upper()
        }
        hit = _only(confirmed)
        if hit:
            out[code] = Match(hit, _RUNG_SIZE_DROP)
            written.append((code, hit, _RUNG_SIZE_DROP))

    if remember and written:
        _remember(db, supplier_id, written, actor=actor)
    return out


def _remember(
    db: Session,
    supplier_id: str,
    binds: list[tuple[str, str, str]],
    *,
    actor: Optional[str],
) -> None:
    """Write the worked-out binds down as `auto` aliases. Does not commit.

    `ON CONFLICT DO NOTHING` against the identity index: two uploads racing on the same code
    is a duplicate, not a failure, and the second one's answer is the same as the first's.
    """
    for code, product_id, rung in binds:
        db.execute(
            text(
                """
                INSERT INTO scm.supplier_product_code_alias
                    (id, company_id, supplier_id, supplier_code, product_id, source,
                     matched_by, created_by, created_at)
                SELECT :id, p.company_id, :supplier_id, :code, :product_id, 'auto',
                       :rung, :actor, now()
                FROM products p WHERE p.id = :product_id
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "supplier_id": str(supplier_id),
                "code": code.strip(),
                "product_id": str(product_id),
                "rung": rung,
                "actor": actor,
            },
        )
    db.flush()
