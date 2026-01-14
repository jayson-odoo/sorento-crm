# Sorento CRM FastAPI Backend

FastAPI backend for Sorento CRM system, migrated from Next.js API routes.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy environment variables:
```bash
cp .env.example .env
```

3. Update `.env` with your database credentials and JWT secret (must match NextAuth secret).

4. Run database migrations:
```bash
alembic upgrade head
```

5. Start the development server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
sorento_crm_backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Configuration settings
│   ├── database.py          # SQLAlchemy setup
│   ├── dependencies.py      # Shared dependencies (auth, DB)
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic schemas
│   ├── api/                 # API routes
│   │   └── v1/              # API version 1
│   └── services/            # Business logic
├── alembic/                 # Database migrations
├── requirements.txt
└── .env
```

## Authentication

The FastAPI backend validates JWT tokens created by NextAuth. The JWT secret must match between Next.js and FastAPI.

Tokens are sent in the `Authorization` header as:
```
Authorization: Bearer <token>
```

## API Routes

All business logic APIs are under `/api/v1/`:
- `/api/v1/master-data/*` - Products, brands, categories, UOM
- `/api/v1/order-management/*` - Orders, customers, order statuses
- `/api/v1/inventory/*` - Warehouses, stock, storage zones
- `/api/v1/procurement/*` - Suppliers, packing lists, GRN, SPO allocations
- `/api/v1/marketing/*` - Promotions, campaigns
- `/api/v1/forms-management/*` - Forms, sections, fields
- `/api/v1/complaint-management/*` - Complaints
- `/api/v1/sla-management/*` - SLA policies, tracking
- `/api/v1/resource-management/*` - Attachments
- `/api/v1/user-management/*` - Users, roles, permissions (business logic only)

Auth routes remain in Next.js:
- `/api/auth/*` - NextAuth endpoints

## Development

### Running Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

### Testing

```bash
# Run tests (when implemented)
pytest
```

## Deployment

The FastAPI backend can be deployed using:
- Docker
- Gunicorn with Uvicorn workers
- Cloud platforms (AWS, GCP, Azure)

Example with Gunicorn:
```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```
