# AGENTS.md

## Cursor Cloud specific instructions

### Project overview
Sorento CRM is a monorepo with two services:
- **Frontend** (`sorento_crm_frontend/`): Next.js 15 + React 19 + Prisma + NextAuth on port 3000
- **Backend** (`sorento_crm_backend/`): FastAPI + SQLAlchemy on port 8000

Standard setup/run commands are documented in the root `README.md`.

### Service startup

**PostgreSQL** must be running before either service. Start with:
```
sudo pg_ctlcluster 16 main start
```

**Backend** (from `sorento_crm_backend/`):
```
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend** (from `sorento_crm_frontend/`):
```
npm run dev
```

### Non-obvious caveats

- **`npm install --force` is required** for the frontend due to React 19 peer dependency conflicts. Do not use `npm install` without `--force`.
- **Prisma uses `text` for UUID columns** while Alembic migrations use `postgresql.UUID`. On a fresh database, use `Base.metadata.create_all()` from SQLAlchemy to create tables, then stamp Alembic to head (`alembic stamp head`), rather than running `alembic upgrade head` which will fail on UUID/text type mismatches. See the database setup section below.
- **`NEXT_PUBLIC_API_URL=http://localhost:8000`** must be set in `sorento_crm_frontend/.env.local` for the frontend to communicate with the backend. If left empty, the Next.js rewrites proxy is used but JWT auth headers don't pass through correctly for some pages.
- **JWT secrets must match**: `JWT_SECRET` in backend `.env` must equal `NEXTAUTH_SECRET` in frontend `.env.local`.
- **Frontend lint** (`npm run lint`) reports ~256 pre-existing errors (mostly `no-explicit-any`, `no-unused-vars`). These are ignored during builds via `eslint.ignoreDuringBuilds: true` in `next.config.mjs`.
- **The Prisma seed script** (`prisma/setup.js`) has a bug referencing `tx.setting.create()` which doesn't exist. The transaction rolls back. Seed the database via direct SQL instead.
- **Backend Python venv** is at `sorento_crm_backend/.venv`. Always activate it before running backend commands.

### Fresh database setup (if needed)

```bash
# 1. Start PostgreSQL
sudo pg_ctlcluster 16 main start

# 2. Create database (if not exists)
sudo -u postgres psql -c "CREATE USER sorento WITH PASSWORD 'sorento123' SUPERUSER;" 2>/dev/null
sudo -u postgres psql -c "CREATE DATABASE sorento_crm OWNER sorento;" 2>/dev/null

# 3. Create all tables via SQLAlchemy
cd /workspace/sorento_crm_backend
source .venv/bin/activate
python3 -c "from app.database import Base, engine; from app.models import *; Base.metadata.create_all(engine)"

# 4. Create Prisma-only tables (accounts, sessions) and enum types
sudo -u postgres psql -d sorento_crm -c "
CREATE TYPE IF NOT EXISTS \"UserStatus\" AS ENUM ('INACTIVE', 'ACTIVE', 'BLOCKED');
CREATE TYPE IF NOT EXISTS \"BatchStatus\" AS ENUM ('AVAILABLE', 'RESERVED', 'DAMAGED', 'EXPIRED', 'RETURNED');
CREATE TYPE IF NOT EXISTS \"CampaignStatus\" AS ENUM ('PLANNING', 'ACTIVE', 'COMPLETED', 'CANCELLED');
ALTER TABLE users ALTER COLUMN status TYPE \"UserStatus\" USING status::\"UserStatus\";
ALTER TABLE stock_batches ALTER COLUMN status TYPE \"BatchStatus\" USING status::\"BatchStatus\";
ALTER TABLE marketing_campaigns ALTER COLUMN status TYPE \"CampaignStatus\" USING status::\"CampaignStatus\";
CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, type TEXT NOT NULL, provider TEXT NOT NULL, provider_account_id TEXT NOT NULL, refresh_token TEXT, access_token TEXT, expires_at INTEGER, token_type TEXT, scope TEXT, id_token TEXT, session_state TEXT);
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text, session_token TEXT NOT NULL UNIQUE, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires TIMESTAMP(3) NOT NULL);
"

# 5. Stamp Alembic migrations
cd /workspace/sorento_crm_backend
source .venv/bin/activate
alembic stamp head

# 6. Generate Prisma client
cd /workspace/sorento_crm_frontend
npx prisma generate
```

### Test credentials
- **Owner**: `owner@example.com` / `123456`
- **Demo**: `demo@shoplit.com` / `demo123`

### Environment files (gitignored, must be created)
- `sorento_crm_backend/.env` — see root `README.md` for variables
- `sorento_crm_frontend/.env` — contains `DATABASE_URL` for Prisma CLI
- `sorento_crm_frontend/.env.local` — contains `NEXTAUTH_SECRET`, `NEXTAUTH_URL`, `NEXT_PUBLIC_API_URL`
