"""Who did it, in the words a person reads.

Provenance columns across SCM are free text: most writers stamp a name (`_actor(current_user)`
is the rule), but some rows on file were stamped with the caller's id instead, and a screen
that prints one of those shows a UUID at a buyer. One helper, so the two places that resolve
those ids cannot answer differently.

De-provisioned users are NOT filtered out: the question is who decided this, and the answer
does not stop being true when the account is closed.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.scm.supplier_scope import is_uuid


def actor_labels(db: Session, ids: Iterable) -> dict[str, str]:
    """`{user_id: name or email}` for the ids given, in ONE query.

    Callers hand in whatever their column holds, so anything that is not id-shaped is
    dropped here rather than asked about: a page of names costs no query at all, and a page
    of hundreds of ids costs one rather than one each.
    """
    wanted = sorted({str(value) for value in ids if value and is_uuid(str(value))})
    if not wanted:
        return {}
    rows = (
        db.query(User.id, User.name, User.email)
        .filter(User.id.in_(wanted))
        .all()
    )
    labels: dict[str, str] = {}
    for user_id, name, email in rows:
        label = (name or "").strip() or email
        if label:
            labels[str(user_id)] = label
    return labels


def actor_label(value, labels: dict[str, str]) -> Optional[str]:
    """One provenance value as a screen prints it: a name, or nothing.

    A value that is not a user id is already what somebody wrote, and passes through. An id
    nobody answers to resolves to `None`, which renders as the dash - "we do not know who" -
    where the raw id says nothing to anybody and reads as a defect.
    """
    if not value:
        return None
    as_text = str(value)
    if not is_uuid(as_text):
        return value
    return labels.get(as_text)
