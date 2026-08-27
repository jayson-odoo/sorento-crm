"""What the supplier calls a product, and what we call it (R16, F11).

Suppliers do not write our codes. Measured on the uploaded JINBAICHUAN stock list, 79 codes
bound to nothing on an exact match, and the reasons are four:

  * the separators are theirs (`SRTWC8357RL` for our `SRTWC8357-RL`);
  * the tokens come in another order (`SRTWC8357-RL-300` for `SRTWC8357-300-RL`) - 4 of them;
  * a trap size is spelled out that our code omits because it is the default
    (`SRTWC8357-RL-250` for `SRTWC8357-RL`, whose description reads `S-TRAP 250MM`);
  * a suffix is glued on after it (`SRTWC286-SH-250UF`, `...-250NEW`).

A LADDER, first unique hit wins, and an ambiguous rung binds NOTHING:

  0. an alias somebody already recorded for THIS supplier - including a DISMISSAL, a row
     with no product, which is the answer "that code names nothing we hold" and stops the
     ladder where it stands;
  1. exact `product_code`;
  2. separator-normalised equality (`entity_resolver._norm_sql`, the expression migration 410
     indexes - shared rather than re-spelled, because two spellings of one rule drift);
  3. token-set reorder - the same tokens, any order;
  4. the trap size dropped, and ONLY where the base product's own description carries that
     size. Without that question the rung finds 28 and 16 of them are wrong: `CWC7606-SH-180`
     is not `CWC7606-SH`, which is the 250. Silence counts as a no.

Then three more rungs, against our product SETS (R19, R20), because a supplier sells the
whole WC: `CWC605-RL` names our SET - pedestal `CWCX605-RL` plus cistern `CWCY605` - and no
product carries that code, so every rung above misses it by construction.

  5. exact `product_sets.set_code`;
  6. separator-normalised equality;
  7. token-set reorder.

There is deliberately NO size rung for sets. `CWC605-RL-180` stays unmatched: a set carries
no description, so nothing can confirm whether 180 is a real variant of ours or the
supplier's own trap size, and rung 4 only earned its size drop by asking the base product
whether it IS that size. A person answers those from the picker instead.

The set rungs run LAST, so a code our catalogue holds verbatim is that product whatever else
happens to be spelled the same way. They are also scoped STRICTLY to the supplier's own
company: a Sorento supplier's list naming a Mocha set code binds nothing, because the stock
rows, the invoice lines and the alias about to be written all belong to Sorento.

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
from app.models.product_set import ProductSet
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
_RUNG_SET_EXACT = "set_exact"
_RUNG_SET_SEPARATOR = "set_separator"
_RUNG_SET_TOKEN_SET = "set_token_set"

#: The rungs whose answer is a DERIVATION rather than an agreement, so it is remembered.
_REMEMBERED = (_RUNG_SEPARATOR, _RUNG_TOKEN_SET, _RUNG_SIZE_DROP)


@dataclass(frozen=True)
class Match:
    """One bound code: what it names, and which rung found it.

    Exactly one of `product_id` / `product_set_id` is set - a code means one thing, and a
    caller choosing between two would be choosing which of them to write on a stock row that
    has one column for each.
    """

    product_id: Optional[str]
    rung: str
    product_set_id: Optional[str] = None


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
    aliases: dict[str, tuple[Optional[str], Optional[str]]] = {}
    for row in (
        db.query(SupplierProductCodeAlias)
        .filter(
            SupplierProductCodeAlias.supplier_id == str(supplier_id),
            SupplierProductCodeAlias.supplier_code.isnot(None),
        )
        .all()
    ):
        aliases[str(row.supplier_code).strip().upper()] = (
            str(row.product_id) if row.product_id else None,
            str(row.product_set_id) if row.product_set_id else None,
        )
    unresolved: list[str] = []
    for code in wanted:
        key = code.strip().upper()
        if key in aliases:
            product_id, set_id = aliases[key]
            # A row naming NOTHING is a DISMISSAL (R17): somebody has said this code names
            # nothing we hold, and that is an answer, so the ladder stops here. Falling
            # through to the worked-out rungs would bind it on the next upload and the
            # dismissal would read as if it had never been made.
            if product_id or set_id:
                out[code] = Match(product_id, _RUNG_ALIAS, product_set_id=set_id)
            continue
        unresolved.append(code)
    if not unresolved:
        return out

    home = _supplier_company(db, supplier_id)
    candidates = _candidates(db, unresolved, home=home)
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

    sets = _set_index(db, home=home)

    def _product_ladder(trimmed: str, tokens: list[str]):
        """Rungs 1-4. `(product_id, rung)` on a bind, `("", "")` on a refusal (this code IS
        ours and we cannot say which one), `None` when nothing here answers it at all."""
        # -- rung 1: exact -----------------------------------------------------------
        hit = _only(by_exact.get(trimmed.upper(), set()))
        if hit:
            return hit, _RUNG_EXACT
        if by_exact.get(trimmed.upper()):
            return "", ""  # two products carry this very code: not ours to choose between

        # -- rung 2: their separators, not ours ---------------------------------------
        pool = by_norm.get(_norm(trimmed), set())
        if pool:
            hit = _only(pool)
            return (hit, _RUNG_SEPARATOR) if hit else ("", "")

        # -- rung 3: the same tokens, another order -----------------------------------
        pool = by_tokens.get(tuple(sorted(tokens)), set())
        if pool:
            hit = _only(pool)
            return (hit, _RUNG_TOKEN_SET) if hit else ("", "")

        # -- rung 4: the trap size ours omits, if the product says it is that size ----
        if not tokens:
            return None
        size = _size_of(tokens[-1])
        if size is None:
            return None
        pool = by_tokens.get(tuple(sorted(tokens[:-1])), set())
        confirmed = {
            pid for pid in pool if f"{size}MM" in (described.get(pid) or "").upper()
        }
        hit = _only(confirmed)
        return (hit, _RUNG_SIZE_DROP) if hit else None

    written: list[tuple[str, str, str, bool]] = []
    for code in unresolved:
        trimmed = code.strip()
        tokens = [t.upper() for t in _tokens(trimmed)]

        answer = _product_ladder(trimmed, tokens)
        if answer is not None:
            product_id, rung = answer
            if product_id:
                out[code] = Match(product_id, rung)
                if rung in _REMEMBERED:
                    written.append((code, product_id, rung, False))
            # A refusal is an ANSWER: the code is one of ours and we cannot say which one.
            # Falling through to the set rungs would answer a question about products with
            # a set, which is a different claim, not a weaker one.
            continue

        # -- rungs 5-7: our SET codes (R19, R20) -------------------------------------
        # No size rung here on purpose - a set carries no description to confirm a size
        # against, so `CWC605-RL-180` stays for a person to answer.
        set_id, rung = _set_ladder(sets, trimmed, tokens)
        if set_id:
            out[code] = Match(None, rung, product_set_id=set_id)
            # ALWAYS written down, exact included - unlike a product exact match, nothing in
            # the catalogue carries this code, so the binding is invisible unless it is
            # recorded, and every screen that says what a code means reads the alias table.
            written.append((code, set_id, rung, True))

    if remember and written:
        _remember(db, supplier_id, written, actor=actor)
    return out


def _set_index(db: Session, *, home: Optional[str]) -> dict[str, dict[str, set[str]]]:
    """Our ACTIVE set codes, indexed the three ways the set rungs ask about them.

    Every active set is read rather than probed for: there are two orders of magnitude fewer
    sets than products (88 on the dev copy), so a token probe would be machinery bought for
    nothing.

    Scoped STRICTLY to the supplier's own company, which is stronger than the product side's
    "prefer home" rule and deliberately so (AC-F12.8). Our companies hold the same PRODUCT
    codes twice over, so one spelling seen once per company is one product wearing one name;
    set codes carry no such twinning, and a Sorento supplier's list naming a Mocha set code
    is naming something that is not ours to bind.
    """
    query = db.query(ProductSet).filter(ProductSet.is_active.is_(True))
    if home:
        query = query.filter(ProductSet.company_id == str(home))
    index: dict[str, dict[str, set[str]]] = {"exact": {}, "norm": {}, "tokens": {}}
    for row in query.all():
        sid = str(row.id)
        code = (row.set_code or "").strip()
        if not code:
            continue
        index["exact"].setdefault(code.upper(), set()).add(sid)
        index["norm"].setdefault(_norm(code), set()).add(sid)
        index["tokens"].setdefault(
            tuple(sorted(t.upper() for t in _tokens(code))), set()
        ).add(sid)
    return index


def _set_ladder(
    sets: dict[str, dict], trimmed: str, tokens: list[str]
) -> tuple[Optional[str], str]:
    """Rungs 5-7, the product rungs' three questions asked of `product_sets.set_code`."""
    for key, rung in (
        (trimmed.upper(), _RUNG_SET_EXACT),
        (_norm(trimmed), _RUNG_SET_SEPARATOR),
        (tuple(sorted(tokens)), _RUNG_SET_TOKEN_SET),
    ):
        bucket = "exact" if rung == _RUNG_SET_EXACT else (
            "norm" if rung == _RUNG_SET_SEPARATOR else "tokens"
        )
        pool = sets[bucket].get(key, set())
        if pool:
            # Two sets answering one code cannot both be what the supplier meant, and the
            # rungs below would answer the same ambiguity a looser way.
            return _only(pool), rung
    return None, ""


def _remember(
    db: Session,
    supplier_id: str,
    binds: list[tuple[str, str, str, bool]],
    *,
    actor: Optional[str],
) -> None:
    """Write the worked-out binds down as `auto` aliases. Does not commit.

    `(code, target id, rung, is_set)`. The company is read off the thing being bound - a
    product or a set - so the memory is filed where the people who will read it can see it.

    `ON CONFLICT DO NOTHING` against the identity index: two uploads racing on the same code
    is a duplicate, not a failure, and the second one's answer is the same as the first's.
    """
    for code, target_id, rung, is_set in binds:
        column, table = (
            ("product_set_id", "product_sets") if is_set else ("product_id", "products")
        )
        db.execute(
            text(
                f"""
                INSERT INTO scm.supplier_product_code_alias
                    (id, company_id, supplier_id, supplier_code, {column}, source,
                     matched_by, created_by, created_at)
                SELECT :id, t.company_id, :supplier_id, :code, :target_id, 'auto',
                       :rung, :actor, now()
                FROM {table} t WHERE t.id = :target_id
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "supplier_id": str(supplier_id),
                "code": code.strip(),
                "target_id": str(target_id),
                "rung": rung,
                "actor": actor,
            },
        )
    db.flush()
