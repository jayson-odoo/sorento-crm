"""Make sure a costing write is attributed to the person who made it.

A staff request already has its audit actor stamped on the session by `get_current_user`
(`app.dependencies._stamp_session_actor`), and then this does nothing. A caller that reaches the
service without that stamp (a script, a test that stands in for the login) would otherwise write
audit rows with no user, shown as "System"; this stamps the named user for the length of the write
and puts back whatever was there.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy.orm import Session


@contextmanager
def acting(db: Session, user_id: Optional[str]) -> Iterator[None]:
    from app.audit_context import AuditActor, actor_scope

    if not user_id or db.info.get("audit_actor") is not None:
        yield
        return
    with actor_scope(AuditActor(actor_type="user", user_id=str(user_id), real_user_id=str(user_id)), db=db):
        yield
