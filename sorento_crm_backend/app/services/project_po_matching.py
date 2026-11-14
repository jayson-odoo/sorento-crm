"""PO-UPLOAD-MATCHING: suggest a product for every PO line the exact tiers could not place.

Matching runs in three steps. The first two are exact and live on the lifecycle
(``POIntakeLifecycleMixin._resolve_product``): the catalogue code, then the customer's
remembered code. Everything still unmatched comes here, in batches of at most
``MATCH_BATCH_SIZE`` lines, and goes to ONE model call per batch (``ask_line_matcher``,
prompt key ``po_line_matcher``). Each line is offered its own candidates:

* ``quotation`` - the products on the PO's quotation version (bound, or the one confirm
  would bind);
* ``customer_map`` - the products this customer's remembered codes point at;
* ``catalogue`` - the catalogue shortlist ``entity_resolver.resolve_references`` returns for
  the line's code-shaped text (exact tier plus its "did you mean" alternatives), resolved
  ONCE per batch and scoped to the PO's company.

The model only chooses: a code it names that the line was not offered is dropped, pick and
options alike. A pick is a SUGGESTION (``resolution_source = "suggested"``) a person
accepts; its confidence and options are kept on the version under
``extracted_json["line_matches"][str(line_no)]``. A batch that fails for any reason leaves
its own lines unmatched and never fails the read.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.project_so import ProjectPOLine, ProjectPOVersion
from app.models.projects import ProjectQuotationLine
from app.services import customer_code_map
from app.services.entity_resolver import resolve_references
from app.services.project_po_reading import (
    _CODE_TOKEN,
    _looks_like_code,
    _nullable,
    _strict_object,
)

logger = logging.getLogger(__name__)

PROMPT_KEY = "po_line_matcher"
MATCH_BATCH_SIZE = 40
CONFIDENCES = ("high", "medium", "low")
SOURCE_QUOTATION = "quotation"
SOURCE_CUSTOMER_MAP = "customer_map"
SOURCE_CATALOGUE = "catalogue"
RESOLUTION_SUGGESTED = "suggested"

# A text-only answer for 40 lines; the reader's own pages take far longer.
_MATCHER_TIMEOUT_SECONDS = 90.0

LINE_MATCHER_SCHEMA: Dict[str, Any] = _strict_object(
    {
        "matches": {
            "type": "array",
            "items": _strict_object(
                {
                    "line_no": {"type": "integer"},
                    "product_code": _nullable("string"),
                    "confidence": {"type": "string", "enum": list(CONFIDENCES)},
                    "options": {"type": "array", "items": {"type": "string"}},
                }
            ),
        }
    }
)

# A code broken by a stray space before or after its dash ("SRTWC8518 -SH") is one code.
_SPACED_DASH = re.compile(r"\s*-\s*")


# ------------------------------------------------------------------ the model call


def ask_line_matcher(db: Session, lines: List[dict], *, company_id: Optional[str]) -> List[dict]:
    """The ONE model call: pick each line's product among its own candidates.

    ``lines`` items are ``{line_no, stock_code, description, candidates: [{code, name,
    source}]}``. Returns ``[{line_no, product_code | None, confidence, options}]``. Raises on
    any failure (no key, provider error, timeout, an answer that is not the schema); the
    caller treats a raise as "this batch stays unmatched".

    Candidates every line of the batch shares are sent once, under
    ``candidates_for_every_line``, not once per line, so a long quotation does not multiply
    into every item; ``lines[].candidates`` carries only what is offered to that line alone.
    The prompt names both keys, and a line may pick from either. ``company_id`` is the PO's
    company, for the log line: the candidates were already scoped to it by the caller.
    """
    from app.services.ai_prompt_registry import agent_model, get_prompt
    from app.services.document_extraction import _assistant_config, _reader_model
    from app.services.llm_provider import get_provider, resolve_api_key

    provider_name, model = agent_model(db, PROMPT_KEY)
    if not provider_name:
        provider_name, model = _reader_model(db)
    api_key = resolve_api_key(_assistant_config(db), provider_name)
    if not api_key:
        raise RuntimeError(f"no API key for the '{provider_name}' provider")
    provider = get_provider(provider_name, api_key, model)

    shared = _shared_candidates(lines)
    shared_codes = {candidate["code"] for candidate in shared}
    payload = {
        "candidates_for_every_line": shared,
        "lines": [
            {
                "line_no": item["line_no"],
                "stock_code": item.get("stock_code"),
                "description": item.get("description"),
                "candidates": [
                    candidate
                    for candidate in item.get("candidates") or []
                    if candidate["code"] not in shared_codes
                ],
            }
            for item in lines
        ],
    }
    system = get_prompt(db, PROMPT_KEY).text
    logger.info(
        "PO line matcher: %s lines, %s shared candidates, company %s, %s/%s",
        len(lines),
        len(shared),
        company_id,
        provider_name,
        model,
    )
    result = provider.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0,
        model=model,
        json_schema=LINE_MATCHER_SCHEMA,
        json_schema_name="po_line_matches",
        timeout=_MATCHER_TIMEOUT_SECONDS,
    )
    data = json.loads((result.content or "").strip())
    matches = data.get("matches") if isinstance(data, dict) else None
    if not isinstance(matches, list):
        raise ValueError("the line matcher answered without a matches list")
    out: List[dict] = []
    for match in matches:
        if not isinstance(match, dict) or match.get("line_no") is None:
            continue
        out.append(
            {
                "line_no": int(match["line_no"]),
                "product_code": match.get("product_code") or None,
                "confidence": match.get("confidence"),
                "options": [str(code) for code in match.get("options") or [] if code],
            }
        )
    return out


def _shared_candidates(lines: Sequence[dict]) -> List[dict]:
    """The candidates present on EVERY line of the batch, in the first line's order."""
    if not lines:
        return []
    common = None
    for item in lines:
        codes = {candidate["code"] for candidate in item.get("candidates") or []}
        common = codes if common is None else common & codes
    return [
        candidate
        for candidate in lines[0].get("candidates") or []
        if candidate["code"] in (common or set())
    ]


# --------------------------------------------------------------- the suggestions


def _products(db: Session, product_ids: Iterable[str]) -> List[Product]:
    ids = sorted({str(pid) for pid in product_ids if pid})
    if not ids:
        return []
    return db.query(Product).filter(Product.id.in_(ids)).all()


def _quotation_candidates(db: Session, quotation_version_id: Optional[str]) -> List[dict]:
    if not quotation_version_id:
        return []
    product_ids = [
        pid
        for (pid,) in db.query(ProjectQuotationLine.product_id)
        .filter(
            ProjectQuotationLine.version_id == quotation_version_id,
            ProjectQuotationLine.is_section.is_(False),
            ProjectQuotationLine.product_id.isnot(None),
        )
        .all()
    ]
    return _candidates_for(_products(db, product_ids), SOURCE_QUOTATION)


def _map_candidates(db: Session, customer_id: Optional[str]) -> List[dict]:
    remembered = customer_code_map.remembered_codes(db, customer_id)
    return _candidates_for(_products(db, remembered.values()), SOURCE_CUSTOMER_MAP)


def _candidates_for(products: Iterable[Product], source: str) -> List[dict]:
    return [
        {
            "code": str(product.product_code),
            "name": product.product_name,
            "source": source,
            "product_id": str(product.id),
        }
        for product in sorted(products, key=lambda p: str(p.product_code or ""))
        if product.product_code
    ]


def line_tokens(stock_code: Optional[str], description: Optional[str]) -> List[str]:
    """What the catalogue shortlist is looked up by: the printed code, and every
    code-shaped token in the description once a stray space around a dash is closed up."""
    tokens: List[str] = []
    code = (stock_code or "").strip().upper()
    if code:
        tokens.append(code)
    text = _SPACED_DASH.sub("-", (description or "").upper())
    for token in _CODE_TOKEN.findall(text):
        if _looks_like_code(token) and token not in tokens:
            tokens.append(token)
    return tokens


def _catalogue_shortlist(
    db: Session, token_lists: List[List[str]], *, company_id: Optional[str]
) -> Dict[str, List[dict]]:
    """token -> catalogue candidates, from ONE ``resolve_references`` call for the batch.

    Exact tier plus its "did you mean" alternatives, products only, inside the PO's company
    scope so another company's row is never offered. A resolver failure is an empty
    shortlist, never a failed read.
    """
    from app.models.base import company_scope

    tokens: List[str] = []
    for token_list in token_lists:
        for token in token_list:
            if token not in tokens:
                tokens.append(token)
    if not tokens:
        return {}
    try:
        with company_scope(db, frozenset({str(company_id)}) if company_id else None):
            result = resolve_references(
                db,
                tokens,
                allowed_entity_types=frozenset({"product"}),
                enable_prefix_fallback=False,
                enable_embedding_fallback=False,
                max_candidates=len(tokens),
                alternatives_active_only=True,
            )
    except Exception:
        logger.exception("PO line matcher: the catalogue shortlist failed for this batch")
        return {}
    out: Dict[str, List[dict]] = {}
    for resolution in result.resolutions:
        found = out.setdefault(resolution.token, [])
        for entity in list(resolution.matches) + list(resolution.alternatives or []):
            if entity.entity_type != "product" or not entity.uuid or not entity.canonical_code:
                continue
            found.append(
                {
                    "code": str(entity.canonical_code),
                    "name": (entity.display or {}).get("product_name"),
                    "source": SOURCE_CATALOGUE,
                    "product_id": str(entity.uuid),
                }
            )
    return out


def _merge(*groups: Iterable[dict]) -> List[dict]:
    """One candidate per product, first source wins (quotation, map, catalogue)."""
    seen: set = set()
    merged: List[dict] = []
    for group in groups:
        for candidate in group:
            if candidate["product_id"] in seen:
                continue
            seen.add(candidate["product_id"])
            merged.append(candidate)
    return merged


def _batches(items: List[Any], size: int) -> List[List[Any]]:
    return [items[start : start + size] for start in range(0, len(items), size)]


def suggest_matches(
    db: Session,
    version: ProjectPOVersion,
    lines: Sequence[ProjectPOLine],
    *,
    customer_id: Optional[str],
    quotation_version_id: Optional[str],
) -> None:
    """Suggest a product for every line in ``lines`` that is still unmatched.

    Writes ``resolved_product_id`` + ``resolution_source = "suggested"`` on a pick and the
    pick's ``{confidence, options}`` under ``extracted_json["line_matches"]``, merged into
    whatever that entry already holds (``qty_suggested``). Options are product ids.
    """
    pending = [
        line
        for line in lines
        if line.resolved_product_id is None
        and not line.is_cancelled
        and ((line.stock_code_raw or "").strip() or (line.description_raw or "").strip())
    ]
    if not pending:
        return

    shared = _merge(
        _quotation_candidates(db, quotation_version_id), _map_candidates(db, customer_id)
    )
    matches: Dict[str, Dict[str, Any]] = dict(
        (version.extracted_json or {}).get("line_matches") or {}
    )

    for batch in _batches(sorted(pending, key=lambda l: l.line_no), MATCH_BATCH_SIZE):
        token_lists = [line_tokens(line.stock_code_raw, line.description_raw) for line in batch]
        shortlist = _catalogue_shortlist(db, token_lists, company_id=version.company_id)
        items: List[dict] = []
        offered: Dict[int, Dict[str, str]] = {}
        for line, tokens in zip(batch, token_lists):
            candidates = _merge(
                shared, *(shortlist.get(token) or [] for token in tokens)
            )
            offered[line.line_no] = {c["code"].upper(): c["product_id"] for c in candidates}
            items.append(
                {
                    "line_no": line.line_no,
                    "stock_code": line.stock_code_raw,
                    "description": line.description_raw,
                    "candidates": [
                        {"code": c["code"], "name": c["name"], "source": c["source"]}
                        for c in candidates
                    ],
                }
            )
        try:
            answers = ask_line_matcher(db, items, company_id=version.company_id)
        except Exception as exc:  # noqa: BLE001 - one bad batch never fails the read
            logger.warning(
                "PO line matcher failed for a batch of %s lines on version %s: %s",
                len(items),
                version.id,
                exc,
            )
            continue

        by_line = {line.line_no: line for line in batch}
        for answer in answers or []:
            try:
                line_no = int(answer.get("line_no"))
            except (TypeError, ValueError):
                continue
            line = by_line.get(line_no)
            if line is None:
                continue
            # Everything this line was offered: the shared list AND its own (`offered` is
            # built from the full per-line list, before `ask_line_matcher` splits it).
            allowed = offered.get(line_no) or {}
            picked = allowed.get(str(answer.get("product_code") or "").strip().upper())
            options: List[str] = []
            for code in answer.get("options") or []:
                product_id = allowed.get(str(code or "").strip().upper())
                if product_id and product_id not in options:
                    options.append(product_id)
            if picked is None and not options:
                continue
            confidence = answer.get("confidence")
            entry = dict(matches.get(str(line_no)) or {})
            entry["confidence"] = confidence if confidence in CONFIDENCES else "low"
            entry["options"] = options
            matches[str(line_no)] = entry
            if picked is not None:
                line.resolved_product_id = picked
                line.resolution_source = RESOLUTION_SUGGESTED

    data = dict(version.extracted_json or {})
    data["line_matches"] = matches
    version.extracted_json = data
    db.flush()
