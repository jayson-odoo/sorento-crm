"""Run a best-effort job AFTER the response has gone out, on its own session.

PS-PROPOSAL-QUOTATION: a project alert fans out per recipient and the notification service
commits per recipient, so sending it inside the request made "Save with reason" wait ~16 s for
17 managers. The route commits its own work, queues the alert here with plain ids, and answers.

The job gets a fresh session (the request's is closed by then) carrying the request's company
scope, so the company-scoped reads it makes see exactly what the request saw.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.models.base import get_company_scope, set_company_scope

logger = logging.getLogger(__name__)


def open_session() -> Session:
    from app.database import SessionLocal

    return SessionLocal()


def close_session(session: Session) -> None:
    session.close()


def _run(scope: Any, job: Callable[..., None], args: tuple, kwargs: dict) -> None:
    session = open_session()
    try:
        set_company_scope(session, scope)
        job(session, *args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("after-response job %s failed (%s)", getattr(job, "__name__", job), exc)
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
    finally:
        close_session(session)


def defer(
    background_tasks: BackgroundTasks,
    request_db: Session,
    job: Callable[..., None],
    *args: Any,
    **kwargs: Any,
) -> None:
    """Queue ``job(session, *args, **kwargs)`` to run after the response is sent."""
    background_tasks.add_task(_run, get_company_scope(request_db), job, args, kwargs)
