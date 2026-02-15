# Backend Standards

This document references the product-wide ADR and highlights backend-specific rules.

**Primary reference:** [ADR-PRODUCT-STANDARDS.md](../../docs/ADR-PRODUCT-STANDARDS.md)

## Delete Semantics
- Delete endpoints perform **hard delete** (permanent removal)
- If retention is needed, provide a separate **Archive** endpoint (e.g. `POST /{id}/archive`)

## Error Responses
- Use consistent format: `{ "detail": "message" }` for 4xx/5xx
- Validation errors: `{ "detail": [{"loc": [...], "msg": "..."}] }` (FastAPI default)

## Service Layer
- Follow SOLID principles; avoid duplication
- Use shared error helpers: `handle_not_found`, `handle_conflict`, `handle_internal_error`
