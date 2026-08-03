"""Dealer Kit module bootstrap.

Registers the module's status-engine entities. The registry ships empty and
every entity arrives from a module bootstrap (``status_engine.registry``), and
the Edition is the FIRST entity in this system to ride the engine - so if
something here looks like it is establishing a convention, it is.

Imported for its side effect from ``app.api.v1.dealer_kit``, which the router
mount loads at startup. Registration is idempotent, so a re-import is free.
"""

MODULE_KEY = "dealer_kit"

EDITION_ENTITY = "dealer_kit_edition"


def _count_editions(db, status_id: str) -> int:
    """How many Editions hold this status.

    Backs "block delete if referenced" in the graph admin: a status still worn
    by a live Edition must not be deletable out from under it.

    Deliberately unscoped by company - this answers "is anything anywhere using
    this status", and a per-company answer would let one company's admin delete
    a status another company's Editions are sitting in.
    """
    from app.models.base import company_scope
    from app.models.dealer_kit import Edition

    with company_scope(db, None):
        return db.query(Edition).filter(Edition.status_id == status_id).count()


def _migrate_editions(db, from_status_id: str, to_status_id: str) -> int:
    """Move every Edition off one status onto another.

    ``status_key`` is carried with it. The two are denormalised copies of one
    fact and the partial unique index that keeps one open Edition per page reads
    the KEY, so updating the id alone would leave a row that is ``done`` by
    foreign key and ``approved`` by index - and a second open Edition could then
    be created against the same page.
    """
    from app.models.base import company_scope
    from app.models.dealer_kit import Edition
    from app.models.status import Status

    with company_scope(db, None):
        target_key = db.query(Status.key).filter(Status.id == to_status_id).scalar()
        if target_key is None:
            return 0
        return (
            db.query(Edition)
            .filter(Edition.status_id == from_status_id)
            .update(
                {"status_id": to_status_id, "status_key": target_key},
                synchronize_session=False,
            )
        )


def register() -> None:
    from app.models.dealer_kit import Edition
    from app.status_engine.registry import StatusEntity, register_status_entity

    register_status_entity(
        StatusEntity(
            entity_type=EDITION_ENTITY,
            label="Catalogue Edition",
            module=MODULE_KEY,
            model=Edition,
            status_attr="status_id",
            record_label_attr="name",
            count_records=_count_editions,
            migrate_records=_migrate_editions,
            # No scope_resolver: every Edition resolves the DEFAULT graph. A
            # per-page fork would let one catalogue invent its own approval
            # rules, which is the opposite of what an approval workflow is for.
            required_flags=["is_initial", "is_terminal"],
        )
    )


register()
