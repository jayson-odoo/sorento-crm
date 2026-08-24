# Sorento CRM

A full-stack CRM application with a **Next.js** frontend and **FastAPI** backend. The frontend handles authentication (NextAuth), UI, and Prisma-backed user/session data; the backend provides business logic, reporting, and integrations.

## Repository structure

| Directory | Stack | Purpose |
|-----------|--------|---------|
| `sorento_crm_frontend/` | Next.js 15, React 19, Prisma, NextAuth | Web UI, auth, user/session DB |
| `sorento_crm_backend/` | FastAPI, SQLAlchemy, Alembic | REST API, business logic, migrations |

---

## Prerequisites

- **Node.js** 18.x or higher (LTS recommended)
- **npm** (or yarn/pnpm)
- **Python** 3.11+ (backend)
- **PostgreSQL** (used by both frontend and backend)
- **Redis** (optional; required for backend job queues / RQ)

---

## Backend (FastAPI) setup

### 1. Create a virtual environment (recommended)

```bash
cd sorento_crm_backend
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment variables

Create a `.env` file in `sorento_crm_backend/` (you can copy from `.env.example` if present, or create from the list below).

**Required:**

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string, e.g. `postgresql://user:password@localhost:5432/sorento_crm` |
| `DIRECT_URL` | Optional; direct DB URL for migrations (same as `DATABASE_URL` if not using pooling) |
| `JWT_SECRET` | Secret for JWT validation (must match NextAuth secret used by frontend) |
| `JWT_ALGORITHM` | Default: `HS256` |

**Optional / feature-specific:**

| Variable | Description |
|----------|-------------|
| `API_HOST` | Bind host (default: `0.0.0.0`) |
| `API_PORT` | Port (default: `8000`) |
| `CORS_ORIGINS` | Comma-separated origins, e.g. `http://localhost:3000` |
| `REDIS_URL` | Redis URL for RQ jobs (e.g. `redis://localhost:6379/0`) |
| `AWS_ACCESS_KEY_ID` | For S3 storage |
| `AWS_SECRET_ACCESS_KEY` | For S3 storage |
| `AWS_REGION` | e.g. `us-east-1` |
| `AWS_S3_BUCKET_NAME` | S3 bucket for attachments |
| `CLOUDFRONT_DOMAIN` | CloudFront distribution domain (S3 read path) |
| `CLOUDFRONT_KEY_PAIR_ID` | CloudFront key-pair ID for signed URLs |
| `CLOUDFRONT_PRIVATE_KEY_PATH` | PEM file used to sign CloudFront URLs |
| `STORAGE_DEFAULT_PROVIDER` | `s3` or `r2`. Provider used for new uploads (default: `s3`) |
| `R2_ACCOUNT_ID` | Cloudflare account ID hosting the R2 bucket |
| `R2_ACCESS_KEY_ID` | R2 S3-compatible access key |
| `R2_SECRET_ACCESS_KEY` | R2 S3-compatible secret |
| `R2_BUCKET_NAME` | R2 bucket name for attachments |
| `R2_CDN_DOMAIN` | Cloudflare custom domain mapped to the R2 bucket (e.g. `cdn.sorento.com`) |
| `N8N_WEBHOOK_URL` | n8n webhook URL for integrations |
| `EXTERNAL_API_KEY` | API key for external API access |
| `USE_REMOTE_TIME` | Set to `1` to use remote time in SLA logic |
| `RESPOND_*` | Respond.io integration (API key, base URL, space ID, etc.) |

### 4. Database migrations

From `sorento_crm_backend/`:

```bash
alembic upgrade head
```

### 5. Run the backend

```bash
uvicorn main:app --reload
# or, with module path:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **Swagger UI:** http://localhost:8000/docs  
- **ReDoc:** http://localhost:8000/redoc  

---

## Frontend (Next.js) setup

### 1. Install dependencies

```bash
cd sorento_crm_frontend
npm install
```

If you hit dependency conflicts (e.g. with React 19), try:

```bash
npm install --force
```

### 2. Environment variables

Create `.env` or `.env.local` in `sorento_crm_frontend/`. Use `.env.local` for local overrides (usually gitignored).

**Required for auth and API:**

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL URL for Prisma (NextAuth, user data) |
| `NEXTAUTH_SECRET` | NextAuth encryption secret (align with backend `JWT_SECRET` if sharing tokens) |
| `NEXTAUTH_URL` | App URL, e.g. `http://localhost:3000` |

**API and base path:**

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Backend API base URL, e.g. `http://localhost:8000` (empty if using same-origin proxy) |
| `NEXT_PUBLIC_BASE_PATH` | Base path for API proxy / routing (optional) |

**Optional:**

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth for NextAuth |
| `EXTERNAL_API_KEY` | Expected key for external API routes |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_SENDER`, `SMTP_FROM` | Email (e.g. nodemailer) |
| `STORAGE_*` | S3-compatible storage (bucket, region, keys, endpoint, CDN URL) |
| `RECAPTCHA_SECRET_KEY` / `NEXT_PUBLIC_RECAPTCHA_SITE_KEY` | reCAPTCHA (e.g. signup; reset password does not use it) |
| `FRONTEND_BASE_URL` | Backend: base URL of the frontend app (e.g. `https://fe-sorento.foundryx.my`) for password reset emails |

### 3. Prisma (database and client)

Deploy schema and generate the client:

```bash
npx prisma db push
npx prisma generate
```

(Use `prisma migrate deploy` in production if you use migrations.)

### 4. Run the frontend

```bash
npm run dev
```

App: http://localhost:3000 (or the port shown in the terminal).

---

## Running both (local dev)

1. Start PostgreSQL (and Redis if using backend jobs).
2. **Backend:** from `sorento_crm_backend/`: activate venv, then `uvicorn main:app --reload` (or `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`).
3. **Frontend:** from `sorento_crm_frontend/`: `npm run dev`.
4. Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in the frontend env so the UI talks to the local backend.

---

## Docker (optional)

From the repository root you can run the stack with Docker Compose:

```bash
docker-compose up -d
```

Configure via environment variables or a root `.env` (see `docker-compose.yml` for `DATABASE_URL`, `JWT_SECRET`, `REDIS_URL`, frontend/backend env, etc.). The backend uses Gunicorn + Uvicorn workers in production; the frontend is built and served (e.g. via Nginx) as defined in the Docker setup.

---

## Env files summary

| App | Env file location | Notes |
|-----|-------------------|--------|
| Backend | `sorento_crm_backend/.env` | Loaded by `pydantic-settings` and `python-dotenv` where used |
| Frontend | `sorento_crm_frontend/.env` or `.env.local` | Next.js loads these automatically; `NEXT_PUBLIC_*` is exposed to the client |

There may be `.env.example` files in either project; copy to `.env` and fill in values. Do not commit real `.env` or `.env.local` with secrets.

---

## Further reading

- **Backend:** `sorento_crm_backend/README.md` - API routes, auth, migrations, project layout.
- **Frontend:** `sorento_crm_frontend/README.md` - Metronic/Next.js layout and tooling.
