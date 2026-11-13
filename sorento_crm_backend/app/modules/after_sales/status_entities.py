"""Status-engine entity owned by the After-sales module (service jobs).

Discovered by ``app/status_engine/discovery.py``; core never names this file.
"""
from __future__ import annotations


def register() -> None:
    from app.services.service_job_status_graph import register_service_job_status_entity

    register_service_job_status_entity()
