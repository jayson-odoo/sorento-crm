"""CHATBOT-CODE-MATCH R4 (owner, 12 Nov 2026): a size comes only from a stored value.

A number in a missed code counts as a size ONLY when it equals a value stored on a product
under one of its class's size keys (`head/bare_size.size_key_rows`, the R6-1 rule, in the
key's registry unit). Two things are read here, between the resolver and the gate, for a
missed product code:

* a product whose stored size equals a number in the typed code, and whose code holds the
  rest of the typed parts (`answer.holds_every_typed_part`), is a close code: it is offered,
  never answered ("8152-300-SH" offers TWC8152-SH-300 with 300 stored);
* when any close code holds a stored size, every close code carries one size line in its
  display (`size_line`): the key the typed number matched, else the stored key, else
  "<label>: not recorded". Nothing is assumed: a code with no stored value has no size.

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
    """The product entity's typed `raw` for the resolver's `token`, or None when the token
    is not a product the parser named."""
    from app.services.chatbot.turn.state import token_key

    key = token_key(token)
    for e in jsc.array(jsc.get(parser, "entities")):
        if not isinstance(e, dict) or jsc.js_string(e.get("hint") or "").lower() not in ("", "product"):
            continue
        if key in (token_key(e.get("raw")), token_key(e.get("canonical_code"))):
            return jsc.js_string(e.get("raw") or e.get("canonical_code") or token)
    return None


def _stored_matches(db: Any, rows: list[Any], typed: str) -> list[dict[str, Any]]:
    """Products whose stored size (any size key a class scopes, or a bare-size key) equals a
    number in `typed` and whose code holds every other typed part, as resolver-shaped rows."""
    from sqlalchemy import Float, case, cast, func, or_

    from app.models.product import Product, chat_searchable_products
    from app.models.product_spec import ProductSpecifications
    from app.services.chatbot.head.bare_size import size_key_rows
    from app.services.chatbot.lanes.business.answer import (
        _CODE_PART,
        holds_every_typed_part,
    )

    parts = _CODE_PART.findall(typed)
    # Every class's size keys: the classes any key scopes, read through the one rule.
    classes = {str(c).casefold() for r in rows for c in (getattr(r, "applies_when", None) or {}).get("class") or []}
    keys = [r.spec_key for r in size_key_rows(rows, classes)]
    out: dict[str, dict[str, Any]] = {}
    for i, part in enumerate(parts):
        if not part.isdigit() or not keys:
            continue
        rest = parts[:i] + parts[i + 1 :]
        if not rest:
            continue
        number = float(part)
        conditions = []
        for key in keys:
            stored = ProductSpecifications.values[key]["value"]
            value = cast(case((func.jsonb_typeof(stored) == "number", stored.astext), else_=None), Float)
            conditions.append(value.between(number - 1e-6, number + 1e-6))
        with db.begin_nested():
            found = (
                db.query(Product.id, Product.product_code)
                .join(ProductSpecifications, ProductSpecifications.product_id == Product.id)
                .filter(Product.is_active.is_(True), chat_searchable_products(), or_(*conditions))
                .order_by(Product.product_code)
                .limit(_STORED_MATCH_CAP)
                .all()
            )
        for pid, code in found:
            if str(pid) not in out and holds_every_typed_part("-".join(rest), code):
                out[str(pid)] = {
                    "entity_type": "product",
                    "canonical_code": code,
                    "uuid": str(pid),
                    "match_field": "product_code",
                    "match_tier": "stored_size",
                    "similarity": None,
                    "display": {},
                }
    return list(out.values())


def _size_line(rows: list[Any], values: dict[str, Any], numbers: list[float]) -> tuple[str, bool] | None:
    """The one size line of a product with these stored `values`, and whether it is a stored
    value: the key a typed number matched, else the first key with a stored value, else the
    first size key "not recorded". None when its class has no size key."""
    from app.services.chatbot.head.bare_size import size_key_rows

    cls = jsc.get(jsc.get(values, "class"), "value")
    keys = size_key_rows(rows, {str(cls).casefold()} if cls else set())
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


def _asked_size(parser: dict[str, Any], spec_none: Any) -> str:
    """ "with size 400 mm" for the size `spec_none` says nothing holds: the grounded entity's
    own label, value and unit (the registry key's, `head/bare_size`); "" when not one size."""
    misses = [m for m in jsc.array(spec_none) if isinstance(m, dict)]
    if len(misses) != 1:
        return ""
    for e in jsc.array(jsc.get(parser, "entities")):
        if isinstance(e, dict) and e.get("spec_key") == misses[0].get("key") and e.get("spec_value") == misses[0].get("value"):
            value = _number(e.get("spec_value"))
            if value is None:
                return ""
            label = jsc.js_string(e.get("spec_label") or e.get("spec_key")).strip().lower()
            return f"with {label} {_plain(value)} {jsc.js_string(e.get('spec_unit') or '').strip()}".strip()
    return ""


def _unheld_size_is_a_miss(db: Any, rows: list[Any], parser: dict[str, Any], resolved: dict[str, Any]) -> None:
    """R4 (lead ruling, 12 Nov 2026): a size the parser read that no variant of the code's family
    holds (the route's `spec_none`, `narrow_code_tokens_by_specs`) is never answered with a code
    that has no stored size. Such a code's resolution becomes a miss whose close codes are its
    family (`product_code_family._family_rows`, the same family the narrowing read), so the
    reply is "Couldn't find X" and the family with each one's stored size."""
    from app.models.product import Product
    from app.models.product_spec import ProductSpecifications
    from app.services.chatbot.turn.state import token_key
    from app.services.product_code_family import _CODE_WORD, _family_rows, _fold

    # The rows each typed token matched: per token (OR mode), or the one token's rows (AND mode).
    asked: list[tuple[dict[str, Any] | None, Any, list[Any]]] = [
        (res, res.get("token"), res.get("matches") or [])
        for res in resolved.get("resolutions") or []
        if isinstance(res, dict) and res.get("resolved") is True
    ]
    tokens = resolved.get("tokens") or []
    if isinstance(resolved.get("intersection"), list) and len(tokens) == 1:
        asked.append((None, tokens[0], resolved["intersection"]))
    for res, token, matched in asked:
        if _typed_of(parser, token) is None:
            continue
        exact = [
            m for m in matched
            if isinstance(m, dict) and m.get("entity_type") == "product" and m.get("uuid")
            and token_key(m.get("canonical_code")) == token_key(token)
        ]
        if len(exact) != 1 or not _CODE_WORD.match(_fold(exact[0].get("canonical_code"))):
            continue
        with db.begin_nested():
            values = db.query(ProductSpecifications.values).filter(ProductSpecifications.product_id == str(exact[0]["uuid"])).scalar()
        line = _size_line(rows, values or {}, [])
        if line is None or line[1]:
            continue  # its class has no size key, or the code holds a stored size: answered as today
        codes = [code for code, _values, _text in _family_rows(db, _fold(exact[0]["canonical_code"]), loose=True)]
        with db.begin_nested():
            ids = dict(db.query(Product.product_code, Product.id).filter(Product.product_code.in_(codes)).all())
        family = [
            {"entity_type": "product", "canonical_code": code, "uuid": str(ids[code]), "match_field": "product_code",
             "match_tier": "family", "similarity": None, "display": {}}
            for code in codes if code in ids
        ]
        if len(family) < 2:
            continue
        miss = {"token": token, "resolved": False, "ambiguous": False, "matches": [], "alternatives": family}
        # What was not found is the size, never the code (owner: state only what the data
        # holds): the miss reads "Couldn't find <code> with size <N> <unit>", and the route's
        # separate "None with size" clause has nothing left to say.
        asked_size = _asked_size(parser, resolved.get("spec_none"))
        if asked_size:
            miss[SIZE_ASKED] = asked_size
            resolved["spec_none"] = []
        if res is not None:
            res.update(miss)
        else:
            # AND mode: the one token's rows become that token's miss, in the per-token shape.
            resolved.update({"match_mode": "or", "intersection": [], "by_entity_type": {}, "resolutions": [miss]})
        unresolved = resolved.setdefault("unresolved_tokens", [])
        if token not in unresolved:
            unresolved.append(token)


def annotate(db: Any, parser: dict[str, Any], resolved: dict[str, Any]) -> None:
    """Every missed product code of `resolved` (in place): the products a stored size equal
    to a typed number reaches, first among its close codes, and each close code's size line
    when any of them holds a stored size. Best effort: a failed read changes nothing."""
    from app.models.product_spec import ProductSpecifications
    from app.services.chatbot.lanes.business.answer import _CODE_PART

    if not isinstance(resolved, dict):
        return
    try:
        rows = _size_rows(db)
        if not rows:
            return
        if resolved.get("spec_none"):
            _unheld_size_is_a_miss(db, rows, parser, resolved)
        for res in resolved.get("resolutions") or []:
            if not isinstance(res, dict) or res.get("resolved") is True:
                continue
            typed = _typed_of(parser, res.get("token"))
            if typed is None:
                continue
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
            with db.begin_nested():
                stored = dict(
                    db.query(ProductSpecifications.product_id, ProductSpecifications.values)
                    .filter(ProductSpecifications.product_id.in_([str(a["uuid"]) for a in close]))
                    .all()
                )
            numbers = [float(p) for p in _CODE_PART.findall(typed) if p.isdigit()]
            lines = {
                str(a["uuid"]): _size_line(rows, stored.get(str(a["uuid"])) or {}, numbers) for a in close
            }
            if not any(line and line[1] for line in lines.values()):
                continue  # no close code holds a stored size: not a size question
            for a in close:
                line = lines.get(str(a["uuid"]))
                if line:
                    a["display"] = {**(a.get("display") or {}), "size_line": line[0]}
    except Exception:
        import logging

        logging.getLogger(__name__).warning("chatbot: code sizes did not read", exc_info=True)
