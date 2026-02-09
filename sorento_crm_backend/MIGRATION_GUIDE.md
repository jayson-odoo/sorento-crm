# Database Migration Guide

This guide explains how to run database migrations for the FastAPI backend using Alembic.

## Problem

You're seeing errors when viewing users because the database schema is out of sync with your SQLAlchemy models. Specifically, the `is_responded` column (and potentially other columns) may be missing from the `conversation_sla_tracking` table.

## Solution: Run Alembic Migrations

### Option 1: Using the Migration Script (Recommended)

```bash
cd sorento_crm_backend
python3 run_migration.py
```

### Option 2: Using Alembic Directly

If you have Alembic installed in your environment:

```bash
cd sorento_crm_backend

# Check current database state
alembic current

# Upgrade to latest migration
alembic upgrade head

# Or upgrade to a specific revision
alembic upgrade 001_add_is_responded
```

### Option 3: Using Python Module

```bash
cd sorento_crm_backend
python3 -c "from alembic.config import Config; from alembic import command; cfg = Config('alembic.ini'); command.upgrade(cfg, 'head')"
```

## Creating New Migrations

When you add new fields to your models, create a new migration:

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "Description of changes"

# Or create an empty migration file
alembic revision -m "Description of changes"
```

Then edit the generated migration file in `alembic/versions/` and run:

```bash
alembic upgrade head
```

## Quick Fix: Add Missing User Columns

If you're getting the error `column users.respond_user_id does not exist`, you can run this SQL directly:

```bash
cd sorento_crm_backend
psql $DATABASE_URL -f migrations/add_user_columns.sql
```

Or use the Alembic migration:

```bash
cd sorento_crm_backend
python3 run_migration.py
```

## Current Migrations

### Migration 002: Add Missing User Columns
The migration `002_add_missing_user_columns.py` adds the following columns to the `users` table:
- `respond_user_id` (VARCHAR, nullable)
- `respond_synced` (VARCHAR, default: 'pending')
- `superior_id` (VARCHAR, nullable, with foreign key to users.id)

### Migration 001: Add SLA Tracking Columns
The migration `001_add_is_responded_to_sla_tracking.py` adds the following columns to the `conversation_sla_tracking` table if they don't exist:

- `is_responded` (Boolean, default: false)
- `responded_at` (DateTime, nullable)
- `response_time` (Numeric, nullable)
- `is_resolved` (Boolean, default: false)
- `resolved_at` (DateTime, nullable)
- `resolved_by` (Text, nullable)
- `respond_contact_phone` (Text, required)
- `respond_contact_name` (Text, nullable)
- `synced_to_excel` (Boolean, default: false)
- `last_synced_to_excel` (DateTime, nullable)
- `resolution_duration` (Numeric, nullable)

## Troubleshooting

### Migration fails with "column already exists"

The migration is designed to check if columns exist before adding them, so this shouldn't happen. If it does, you can manually edit the migration file to skip that column.

### Database connection errors

Make sure your `.env` file has the correct `DATABASE_URL` set:

```
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
```

### Need to rollback

To rollback the last migration:

```bash
alembic downgrade -1
```

To rollback to a specific revision:

```bash
alembic downgrade <revision_id>
```

## Notes

- Always backup your database before running migrations in production
- Test migrations in a development environment first
- The migration script checks for existing columns before adding them, so it's safe to run multiple times
