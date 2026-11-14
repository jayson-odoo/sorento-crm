"""CHATBOT-CODE-MATCH R4 (owner, 12 Nov 2026): a size comes only from a stored value.

A number in a missed code counts as a size ONLY when it equals a value stored on a product
under one of its class's size keys (`head/bare_size.size_key_rows`, the R6-1 rule, in the
key's registry unit). Two things are read here, between the resolver and the gate, for a
missed product code:

* a product whose stored size equals a number in the typed code, and whose code holds the
  rest of the typed parts (`answer.holds_every_typed_part`), is a close code: it is offered,
  never answered ("8152-300-SH" offers TWC8152-SH-300 with 300 stored);
* a size the parser read apart from the code that the code does not store is never answered
  with that code: its resolution becomes a miss ("Couldn't find X with size 400 mm") whose
  close codes are what the generic code probe finds for the typed code
  (`entity_resolver._prefix_probe_product`), a family of one included;
* when any close code holds a stored size, or the miss is a size miss, every close code
  carries one size line in its display (`size_line`): the key the typed number matched, else
  the stored key, else "<label>: not recorded". Nothing is assumed.

Data only: no company letter, size marker or key name is read.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot import jsc

#: How many products one stored-size probe may offer for a number (the offer shows 3).
_STORED_MATCH_CAP = 20


def _plain(number: float) -> int | float:
    return int(number) if float(number).is_integer() else number


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _size_rows(db: Any) -> list[Any]:
    from app.services.product_spec_registry import active_registry

    return [
        r for r in active_registry(db)
        if (r.data_type or "").lower() == "numeric" and getattr(r, "unit", None)
    ]


def _typed_of(parser: dict[str, Any], token: Any) -> str | None:
    """The word typed for the resolver's `token` (`turn_runtime.typed_by_token`, the one
    lookup), or None when the message typed none."""
    from app.services.chatbot.turn.state import token_key
    from app.services.chatbot.turn_runtime import typed_by_token

    return typed_by_token(jsc.array(jsc.get(parser, "entities"))).get(token_key(token)) or None


def _stored_matches(db: Any, rows: list[Any], typed: str) -> list[dict[str, Any]]:
    """Products whose stored size equals a number in `typed`, under a size key of the product's
    own class (`bare_size.size_key_applies`), and whose code holds every other typed part in
    order (`answer.typed_code_parts`, the slice 2 rule, read in the query before its bound)."""
    from sqlalchemy import Float, and_, case, cast, func, or_

    from app.models.product import (
        Product,
        ProductCategory,
        chat_searchable_products,
        offerable_products,
    )
    from app.models.product_spec import ProductSpecifications
    from app.services.chatbot.lanes.business.answer import typed_code_parts

    parts = typed_code_parts(typed)
    categories = ProductCategory.__table__  # Core, so the company listener cannot hide a shared category
    product_class = func.lower(func.coalesce(ProductSpecifications.values["class"]["value"].astext, categories.c.class_label))
    folded_code = func.lower(func.regexp_replace(Product.product_code, "[^[:alnum:]]", "", "g"))
    out: dict[str, dict[str, Any]] = {}
    for i, part in enumerate(parts):
        rest = parts[:i] + parts[i + 1 :]
        if not part.isdigit() or not rest:
            continue
        number = float(part)
        conditions = []
        for row in rows:
            stored = ProductSpecifications.values[row.spec_key]["value"]
            value = cast(case((func.jsonb_typeof(stored) == "number", stored.astext), else_=None), Float)
            equal = value.between(number - 1e-6, number + 1e-6)
            scope = [str(c).casefold() for c in (getattr(row, "applies_when", None) or {}).get("class") or []]
            if scope:
                conditions.append(and_(equal, product_class.in_(scope)))
            elif getattr(row, "matches_bare_size", False):
                conditions.append(equal)
        if not conditions:
            continue
        escaped = [p.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") for p in rest]
        with db.begin_nested():
            found = (
                db.query(Product.id, Product.product_code)
                .join(ProductSpecifications, ProductSpecifications.product_id == Product.id)
                .outerjoin(categories, categories.c.id == Product.category_id)
                .filter(
                    offerable_products(),
                    chat_searchable_products(),
                    folded_code.like("%" + "%".join(escaped) + "%", escape="\\"),
                    or_(*conditions),
                )
                .order_by(Product.product_code)
                .limit(_STORED_MATCH_CAP)
                .all()
            )
        for pid, code in found:
            out.setdefault(str(pid), _row(code, str(pid), "stored_size"))
    return list(out.values())


def _row(code: str, uuid: str, tier: str) -> dict[str, Any]:
    return {
        "entity_type": "product", "canonical_code": code, "uuid": uuid, "match_field": "product_code",
        "match_tier": tier, "similarity": None, "display": {},
    }


def _product_facts(db: Any, ids: list[str]) -> dict[str, tuple[dict[str, Any], str]]:
    """`{product id: (stored spec values, class)}`: the class is the stored spec class, else the
    product category's class (the class a product with no spec row is filed under)."""
    from app.models.product import Product, ProductCategory
    from app.models.product_spec import ProductSpecifications

    categories = ProductCategory.__table__  # Core, so the company listener cannot hide a shared category
    with db.begin_nested():
        found = (
            db.query(Product.id, ProductSpecifications.values, categories.c.class_label)
            .outerjoin(ProductSpecifications, ProductSpecifications.product_id == Product.id)
            .outerjoin(categories, categories.c.id == Product.category_id)
            .filter(Product.id.in_(ids))
            .all()
        )
    out: dict[str, tuple[dict[str, Any], str]] = {}
    for pid, values, class_label in found:
        values = values if isinstance(values, dict) else {}
        cls = jsc.js_string(jsc.get(jsc.get(values, "class"), "value") or class_label or "")
        out[str(pid)] = (values, cls.casefold())
    return out


def _size_line(rows: list[Any], facts: tuple[dict[str, Any], str] | None, numbers: list[float]) -> tuple[str, bool] | None:
    """The one size line of a product with these stored values and class, and whether it is a
    stored value: the key a typed number matched, else the first key with a stored value, else
    the first size key "not recorded". None when its class has no size key."""
    from app.services.chatbot.head.bare_size import size_key_rows

    values, cls = facts or ({}, "")
    keys = size_key_rows(rows, {cls} if cls else set())
    if not keys:
        return None
    stored = {r.spec_key: _number(jsc.get(jsc.get(values, r.spec_key), "value")) for r in keys}
    matched = [r for r in keys if stored[r.spec_key] is not None and any(abs(stored[r.spec_key] - n) < 1e-6 for n in numbers)]
    held = [r for r in keys if stored[r.spec_key] is not None]
    row = (matched or held or keys)[0]
    if stored[row.spec_key] is None:
        return f"{row.label}: not recorded", False
    return f"{row.label}: {_plain(stored[row.spec_key])} {row.unit}".strip(), True


#: The resolution key a size miss carries: the size asked, as "with size 400 mm".
SIZE_ASKED = "size_asked"
#: The catalogue code a size miss is about (the code exists; the size is what is missing).
SIZE_CODE = "size_code"


def _product_codes(parser: dict[str, Any]) -> list[dict[str, Any]]:
    """The product codes this message names (parser entities, hint product)."""
    return [
        e for e in jsc.array(jsc.get(parser, "entities"))
        if isinstance(e, dict) and e.get("current_message") is not False and jsc.js_string(e.get("hint") or "").lower() == "product"
    ]


def _named_codes(parser: dict[str, Any]) -> set[str]:
    """The codes the message's product entities name whole, folded by `turn_state.token_key`:
    each one's raw, and the parser's `canonical_code` when `grounding.picked_code_verdict`
    answers it (CHATBOT-CLOSE-CODES AC-36/37, the one decision)."""
    from app.services.chatbot.head.grounding import ANSWER, picked_code_verdict
    from app.services.chatbot.turn.state import token_key

    out: set[str] = set()
    for e in _product_codes(parser):
        raw, canonical = e.get("raw"), e.get("canonical_code")
        if raw:
            out.add(token_key(raw))
        if canonical and picked_code_verdict(e) == ANSWER:
            out.add(token_key(canonical))
    return out - {""}


def _sizes(parser: dict[str, Any]) -> list[dict[str, Any]]:
    """The numeric sizes the parser read apart from a code (grounded specification entities)."""
    return [
        e for e in jsc.array(jsc.get(parser, "entities"))
        if isinstance(e, dict) and e.get("current_message") is not False and e.get("spec_key")
        and _number(e.get("spec_value")) is not None
    ]


def _asked_size(parser: dict[str, Any]) -> tuple[list[str], float, str, str] | None:
    """The one numeric size the parser read beside the message's ONE product code (lead
    re-scope, 12 Nov 2026: several codes and a size keep main's behaviour): the keys it may be
    under, its value, "with size 400 mm" in the key's own label and unit (`head/bare_size`),
    and that code, folded. None otherwise."""
    from app.services.chatbot.turn.state import token_key

    sizes, codes = _sizes(parser), _product_codes(parser)
    if len(sizes) != 1 or len(codes) != 1:
        return None
    e = sizes[0]
    value = _number(e.get("spec_value"))
    keys = [str(k) for k in e.get("spec_any_keys") or [e.get("spec_key")] if k]
    label = jsc.js_string(e.get("spec_label") or e.get("spec_key")).strip().lower()
    said = f"with {label} {_plain(value)} {jsc.js_string(e.get('spec_unit') or '').strip()}".strip()
    return keys, value, said, token_key(codes[0].get("canonical_code") or codes[0].get("raw"))


def _unheld_size_is_a_miss(db: Any, parser: dict[str, Any], resolved: dict[str, Any]) -> None:
    """R4 (lead ruling, 12 Nov 2026): a code the parser named beside a size it does not store is
    never answered as that code. Its resolution becomes a miss ("Couldn't find X with size N")
    whose close codes are what the generic code probe finds for the code as typed
    (`entity_resolver._prefix_probe_product`, prefix then substring), the code itself included,
    so a family of one is still offered; the route's separate "None with size" clause is then
    said by the header and dropped."""
    from app.services.chatbot.turn.state import token_key
    from app.services.entity_resolver import (
        _drop_unofferable_products,
        _prefix_probe_product,
    )

    asked = _asked_size(parser)
    if asked is None:
        return
    keys, value, said, owner = asked
    # The rows each typed token matched: per token (OR mode), or the one token's rows (AND mode).
    named: list[tuple[dict[str, Any] | None, Any, list[Any]]] = [
        (res, res.get("token"), res.get("matches") or [])
        for res in resolved.get("resolutions") or []
        if isinstance(res, dict) and res.get("resolved") is True
    ]
    tokens = resolved.get("tokens") or []
    if isinstance(resolved.get("intersection"), list) and len(tokens) == 1:
        named.append((None, tokens[0], resolved["intersection"]))
    for res, token, matched in named:
        # The row whose code is the message's one code (the route may have cut a spaced
        # "twc8152 sh uf" to its code word first).
        exact = [
            m for m in matched
            if isinstance(m, dict) and m.get("entity_type") == "product" and m.get("uuid")
            and token_key(m.get("canonical_code")) == owner
        ]
        typed = _typed_of(parser, token) or (str(exact[0]["canonical_code"]) if exact else None)
        if typed is None or len(exact) != 1:
            continue
        values = (_product_facts(db, [str(exact[0]["uuid"])]).get(str(exact[0]["uuid"])) or ({}, ""))[0]
        if any(_number(jsc.get(jsc.get(values, k), "value")) == value for k in keys):
            continue  # the code holds the size it was asked with: answered as today
        # The code as typed, else as the resolver matched it (a spaced "twc8152 sh uf" probes
        # as nothing), else the matched code alone: a family of one is still offered.
        family: list[dict[str, Any]] = []
        for probe in dict.fromkeys([typed, str(exact[0]["canonical_code"])]):
            with db.begin_nested():
                probed = _drop_unofferable_products(db, _prefix_probe_product(db, probe))
            family = [_row(p.canonical_code, str(p.uuid), "family") for p in probed if p.uuid and p.canonical_code]
            if family:
                break
        if not family:
            # The code alone, when the chat may offer it (owner Q3); else the miss offers nothing
            # (R4: a code is never answered for a size it does not store).
            alone = _offerable_rows(db, [exact[0]])
            family = [_row(str(r["canonical_code"]), str(r["uuid"]), "family") for r in alone]
        miss = {
            "token": token, "resolved": False, "ambiguous": False, "matches": [], "alternatives": family, SIZE_ASKED: said,
            # The code exists; what is missing is the size, so the reply names the code itself.
            SIZE_CODE: str(exact[0]["canonical_code"]),
        }
        if res is not None:
            res.update(miss)
        else:
            # AND mode: the one token's rows become that token's miss, in the per-token shape.
            resolved.update({"match_mode": "or", "intersection": [], "by_entity_type": {}, "resolutions": [miss]})
        resolved["spec_none"] = []
        unresolved = resolved.setdefault("unresolved_tokens", [])
        if token not in unresolved:
            unresolved.append(token)


def _all_parts_matches(db: Any, typed: str) -> list[dict[str, Any]]:
    """CHATBOT-CODE-MATCH AC-27 (replay round): the close codes whose folded code holds EVERY
    typed part (`answer.typed_code_parts`), in any order, for a typed code with at least one
    digit part: active, chat-searchable, scoped by the session like every product read,
    bounded in the query, closest first. Offers only ("8152-300-SH" offers SRTWC8152-SH-300
    although prefix, substring and trigram miss it); a code missing one part is not one of them.
    The fallback for a miss with no other candidate (`annotate`)."""
    from sqlalchemy import func

    from app.models.product import Product, chat_searchable_products, offerable_products
    from app.services.chatbot.lanes.business.answer import typed_code_parts

    parts = list(dict.fromkeys(typed_code_parts(typed)))
    if not any(p.isdigit() for p in parts):
        return []
    folded_code = func.lower(func.regexp_replace(Product.product_code, "[^[:alnum:]]", "", "g"))
    escaped = [p.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") for p in parts]
    with db.begin_nested():
        found = (
            db.query(Product.id, Product.product_code)
            .filter(
                offerable_products(),
                chat_searchable_products(),
                *(folded_code.like(f"%{p}%", escape="\\") for p in escaped),
            )
            # The closest first, by the trigram score on both folded sides, so the bound never
            # keeps the alphabetically first codes over the nearest ones.
            .order_by(func.similarity(folded_code, "".join(parts)).desc(), Product.product_code)
            .limit(_STORED_MATCH_CAP)
            .all()
        )
    return [_row(code, str(pid), "all_parts") for pid, code in found]


def _offerable_rows(db: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The product rows the chat may offer (`entity_resolver.offerable_product_rows`: offerable and
    chat-searchable, owner Q3; the chat-searchable net is #2397's, pinned by
    tests/chatbot/test_code_match_regfix_2397.py)."""
    from app.services.entity_resolver import offerable_product_rows

    return offerable_product_rows(db, rows)


def _single_substring_is_an_offer(
    db: Any, resolved: dict[str, Any], named_codes: set[str] | frozenset[str] = frozenset(), *, prefix_offer: bool = True
) -> None:
    """CHATBOT-CODE-MATCH AC-27b (lead ruling): a code that is only INSIDE one catalogue code (a
    lone hit the typed code is not the prefix of: "C21120UW-2-MY" inside BRC21120UW-2-MY) is
    offered as "Did you mean X?", never answered. CHATBOT-CLOSE-CODES C2 / AC-6 (crew Q2 (a),
    13 Nov 2026): a lone PREFIX hit is offered the same way ("SRTWC287-S" for SRTWC287-S-150);
    only the equal code (case and separators folded) is answered. Several hits stay today's
    which-one picker. Read per token (OR mode) or on the one token's rows (AND mode), folded as
    the resolver folds (`turn_state.token_key`). A code the message's own product entity names
    whole (`named_codes`: its raw or the parser's code, folded the same way, as in "TWC015SS
    CR" or "SRTWT8259 gun metal" read as SRTWT8259-GM) is that equal code, answered as today.
    `prefix_offer` False (an ask other than stock or incoming) answers a lone prefix as on main."""
    from app.services.chatbot.turn.state import token_key

    def inside_only(token: Any, rows: list[Any]) -> dict[str, Any] | None:
        rows = [m for m in rows if isinstance(m, dict)]
        if len(rows) != 1 or rows[0].get("entity_type") != "product":
            return None
        code, typed = token_key(rows[0].get("canonical_code")), token_key(token)
        if not typed or typed not in code or code == typed or code in named_codes:
            return None
        return rows[0] if prefix_offer or not code.startswith(typed) else None

    named: list[tuple[dict[str, Any] | None, Any, list[Any]]] = [
        (res, res.get("token"), res.get("matches") or [])
        for res in resolved.get("resolutions") or []
        if isinstance(res, dict) and res.get("resolved") is True
    ]
    tokens = resolved.get("tokens") or []
    if isinstance(resolved.get("intersection"), list) and len(tokens) == 1:
        named.append((None, tokens[0], resolved["intersection"]))
    for res, token, rows in named:
        hit = inside_only(token, rows)
        if hit is None:
            continue
        # A code the chat may not offer (owner Q3) leaves today's no-candidate miss.
        miss = {"token": token, "resolved": False, "ambiguous": False, "matches": [], "alternatives": _offerable_rows(db, [hit])}
        if res is not None:
            res.update(miss)
        else:
            resolved.update({"match_mode": "or", "intersection": [], "by_entity_type": {}, "resolutions": [miss]})
        unresolved = resolved.setdefault("unresolved_tokens", [])
        if token not in unresolved:
            unresolved.append(token)


def annotate(db: Any, parser: dict[str, Any], resolved: dict[str, Any]) -> None:
    """Every product code of `resolved` that missed (in place), or that a lone substring hit
    (`_single_substring_is_an_offer`) or a size it does not store (`_unheld_size_is_a_miss`)
    makes a miss: the close codes holding every typed part (`_all_parts_matches`), after the
    resolver's own; the products a stored size equal to a typed number reaches, first among its
    close codes; and each close code's size line when any of them holds a stored size or the
    miss is a size miss. The registry is read only for a miss. Best effort: a failed read
    changes nothing."""
    from app.services.chatbot.head.grounding import CLOSE_CODE_ASKS
    from app.services.chatbot.lanes.business.answer import typed_code_parts

    if not isinstance(resolved, dict):
        return
    # Several codes and a size: main's behaviour for the size rules (lead re-scope, 12 Nov 2026).
    sized = not (_sizes(parser) and len(_product_codes(parser)) > 1)
    try:
        _single_substring_is_an_offer(
            db, resolved, _named_codes(parser), prefix_offer=jsc.get(parser, "domain_hint") in CLOSE_CODE_ASKS
        )
        if sized:
            _unheld_size_is_a_miss(db, parser, resolved)
        misses = [
            (res, typed)
            for res in resolved.get("resolutions") or []
            if isinstance(res, dict) and res.get("resolved") is not True
            and (typed := _typed_of(parser, res.get("token")) or res.get(SIZE_CODE)) is not None
        ]
        for res, typed in misses:
            if any(isinstance(a, dict) for a in [*(res.get("alternatives") or []), *(res.get("matches") or [])]):
                continue  # the any-order tier is the fallback: only for a miss with no other candidate
            res["alternatives"] = _all_parts_matches(db, typed)
        rows = _size_rows(db) if misses and sized else []
        if not rows:
            return
        for res, typed in misses:
            alternatives = [a for a in res.get("alternatives") or [] if isinstance(a, dict)]
            seen = {str(a.get("uuid")) for a in [*alternatives, *(res.get("matches") or [])] if isinstance(a, dict)}
            added = [m for m in _stored_matches(db, rows, typed) if m["uuid"] not in seen]
            if added:
                res["alternatives"] = alternatives = [*added, *alternatives]
            close = [
                a for a in [*(res.get("matches") or []), *alternatives]
                if isinstance(a, dict) and a.get("entity_type") == "product" and a.get("uuid")
            ]
            if not close:
                continue
            facts = _product_facts(db, [str(a["uuid"]) for a in close])
            numbers = [float(p) for p in typed_code_parts(typed) if p.isdigit()]
            lines = {str(a["uuid"]): _size_line(rows, facts.get(str(a["uuid"])), numbers) for a in close}
            if not res.get(SIZE_ASKED) and not any(line and line[1] for line in lines.values()):
                continue  # no close code holds a stored size: not a size question
            for a in close:
                line = lines.get(str(a["uuid"]))
                if line:
                    a["display"] = {**(a.get("display") or {}), "size_line": line[0]}
    except Exception:
        import logging

        logging.getLogger(__name__).warning("chatbot: code sizes did not read", exc_info=True)
