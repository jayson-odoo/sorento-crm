"""Tickets API routes."""
from fastapi import APIRouter

from app.api.v1.tickets import tickets

router = APIRouter()

router.include_router(tickets.router)
