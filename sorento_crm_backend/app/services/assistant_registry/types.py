"""What the assistant may read: one `EntityDef` per list screen (PLAN-ai-tools-standard-5nov.md section 2.1).

The registry states what nothing else enforces on a direct query: the screen's view slug, its "only mine"
narrowing, the field allowlist and the field-level slugs. Company isolation is not stated here: every
`CompanyScopedMixin` model is filtered by `do_orm_execute` on the session that `run_as_user` stamps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class FieldDef:
    label: str
    #: An extra slug needed to read this field (cost price, phone, margin); None = the entity's slug is enough.
    #: `reveal:<key>` names a reveal key instead (`contact_field_reveal_service`), held by a staff member through
    #: the slug of the screen that shows that data (`staff_reveal_keys`): the sales report's own gate.
    permission: str | None = None
    #: The model attribute; None = the field key itself.
    column: str | None = None
    #: One line for crm_describe when the field could be mistaken for another (which list column it is).
    note: str | None = None
    #: A value over the whole record that also covers lines of other brands (an order's total, a complaint's list
    #: of product codes): refused while the session carries a contact's brand scope, whose screen recomputes or
    #: cuts it to the in-scope lines only.
    whole_document: bool = False
    #: () -> SQL expression over the model, taken from the module's own service (the owner's sales figure is
    #: `invoiced_sales.signed_amount`), so the figure is never written twice. Read-only: no `column`.
    expr: Callable[[], Any] | None = None
    #: The field's type on a computed entity (no column to read it from): text, number, date, boolean.
    kind: str | None = None


@dataclass(frozen=True)
class EntityDef:
    key: str
    label: str
    #: Module key for `require_module_enabled` ("scm").
    module: str
    model: type
    #: The list screen's slug. None = a lookup entity: reachable only through a relation, read under the
    #: parent entity's slugs, never listed or queried on its own.
    view_permission: str | None
    #: The screen's ".view_own" slug; a holder of it without `view_permission` sees only `own_clause` rows.
    own_permission: str | None = None
    #: (own_scope.Me) -> SQL clause of the rows that are theirs; None = this entity has no "only mine" rule,
    #: so an own-only holder is refused.
    own_clause: Callable[[Any], Any] | None = None
    #: ALLOWLIST: what the screen shows. Nothing else is readable.
    fields: dict[str, FieldDef] = field(default_factory=dict)
    #: name -> (entity key, fk column on this model), for lookups and joins.
    relations: dict[str, tuple[str, str]] = field(default_factory=dict)
    #: The fields a person names a record by (its number or code, then its name): every row carries them as one
    #: `label`, "CODE: Name", in place of the separate fields.
    name_by: tuple[str, ...] = ()
    #: Filters applied unless the query filters on that field itself: (field, op, value, note). The note is
    #: returned with the result so the answer says what was left out (orders: cancelled ones, owner ruling).
    default_filters: tuple[tuple[str, str, Any, str], ...] = ()
    #: "/scm/purchase-orders/{id}", for row links; "" = no detail page.
    screen_path: str = ""
    #: Path prefixes where this module's actions load first (ACT-CORE).
    pages: tuple[str, ...] = ()
    #: The list routes this entity answers for ("GET /api/v1/scm/purchase-orders"), read by the CI gate.
    routes: tuple[str, ...] = ()
    #: (db) -> extra always-on clauses the screen's own list applies (not deleted, brand scope).
    scope: Callable[[Any], list] | None = None
    #: A computed entity (figures no table holds: a target's achievement and commission). (db, user_id, own_only,
    #: date_from, date_to) -> rows as dicts keyed by field, built by the module's own service; filters, groups
    #: and aggregates then run over them in code (`assistant_registry.computed`). The row's "id" and every
    #: `screen_path` placeholder come from the dict.
    compute: Callable[..., list[dict]] | None = None
    #: A computed entity's date-window field: a filter on it picks which periods `compute` reads (overlap), it is
    #: not a row filter. Without one the window is today, and the result's scope note says so.
    window_field: str | None = None
    #: Figures that cover every brand and cannot be cut to a brand-scoped contact's brands (invoice totals, a
    #: target's achievement): refused while the session carries a brand scope (a linked user's WhatsApp turn).
    brand_blind: bool = False
    #: A slug (or `reveal:<key>`) needed for any group_by or aggregate: totals and rankings are the sales report's
    #: figures, so they follow its gate even where the list screen does not (crew pass, 5 Nov).
    aggregate_permission: str | None = None
    #: One line for the compact entity index in `crm_query`'s description: what the entity is for, so most
    #: questions need no `crm_describe` call (crew pass, 5 Nov: the extra round cost ~28k prompt tokens a turn).
    hint: str = ""
    #: The columns a row shows when the query names no `fields` (crew pass on 69b3b479: a below-target answer
    #: carried 22 columns into the prompt and the table). Empty = every field, as before.
    list_fields: tuple[str, ...] = ()
