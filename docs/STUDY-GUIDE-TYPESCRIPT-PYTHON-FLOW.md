# Study Guide: TypeScript + Python Full-Stack (Product Page Flow)

This guide is for someone preparing for a **JavaScript + Python** technical assessment. It explains why **TypeScript (frontend) + Python (backend)** is a strong choice and walks through a real example in this repo: **how a product page works** from UI → API → database → back to the UI.

---

## Why TypeScript + Python for the Test?

- **TypeScript** = JavaScript with types. It’s what most modern frontends use (React, Next.js, Vue, etc.). The test likely expects JS/TS on the frontend.
- **Python** = Very common for backend/APIs (FastAPI, Django, Flask). The test likely expects Python on the server side.
- **Together** they match real full-stack jobs: TypeScript for UI and API calls, Python for business logic, validation, and database access. This repo is exactly that: **Next.js (TypeScript)** + **FastAPI (Python)**.

So yes: **TypeScript + Python is a good, realistic stack for your friend’s test.**

---

## High-Level: What Happens When You Open a Product Page?

1. **Frontend (TypeScript)**  
   The user opens the product list or a product detail page. A React component runs and needs data.

2. **API call (TypeScript)**  
   The frontend calls a **service function** (e.g. `getProducts()` or `getProduct(id)`), which uses `fetch` to hit the backend.

3. **Backend (Python)**  
   FastAPI receives the HTTP request, runs an **API route** (e.g. `GET /api/v1/master-data/products` or `GET .../products/{id}`).

4. **Service + database (Python)**  
   The route calls a **service** (e.g. `ProductService`). The service uses **SQLAlchemy** to query **PostgreSQL** and returns data.

5. **Response**  
   The route returns JSON. FastAPI serializes the response using **Pydantic** schemas.

6. **Display (TypeScript)**  
   The frontend receives the JSON, stores it (e.g. in React Query), and the React component **renders** the product list or detail.

End-to-end: **Browser → Frontend (TS) → HTTP → Backend (Python) → DB → Backend → HTTP → Frontend (TS) → UI.**

---

## Step-by-Step: Product List and Product Detail

We use the **Products** feature in this repo as the example.

### 1. Frontend: The page and the component

- **List:** `sorento_crm_frontend/app/(protected)/master-data-management/products/page.tsx` renders the products list.
- **Detail:** `.../products/[id]/page.tsx` renders a single product; it gets the `id` from the URL and passes it to `<ProductDetail productId={id} />`.

So:

- **List page** → needs: “all products (with filters/pagination)”.
- **Detail page** → needs: “one product by id”.

### 2. Frontend: Hook that triggers the request

Components don’t call the API directly. They use a **hook** that uses **React Query**:

- **List:** In `ProductsList.tsx`, something like:
  - `useQuery({ queryKey: ['products', pagination, sorting, filters...], queryFn: () => fetchProducts(...) })`.
  - `queryFn` calls the **service** (e.g. `getProducts(params)`).
- **Detail:** In `ProductDetail.tsx`:
  - `useProduct(productId)` → inside it, `useQuery({ queryKey: ['product', id], queryFn: () => getProduct(id) })`.

So: **Component → Hook (useQuery) → Service function.**

### 3. Frontend: Service layer (TypeScript)

The service builds the URL, calls the backend, and returns typed data.

**List:**

- File: `sorento_crm_frontend/app/(protected)/master-data-management/products/services/productService.ts`
- `getProducts(params)`:
  - Builds query string: `page`, `limit`, `sort`, `dir`, `query`, `category_id`, `brand_id`, `status`, etc.
  - Calls: `apiFetch('/api/v1/master-data/products?' + queryParams, { method: 'GET', ... })`
  - Returns: `Promise<ProductApiResponse>` (typed).

**Detail:**

- Same file: `getProduct(id)`:
  - Calls: `apiFetch('/api/v1/master-data/products/' + id, { method: 'GET', ... })`
  - Returns: `Promise<ProductDetail>`.

**`apiFetch`** (in `lib/api.ts`):

- Adds the backend base URL (e.g. `NEXT_PUBLIC_API_URL` in dev) so the full URL might be `http://localhost:8000/api/v1/master-data/products?...`.
- Sends credentials (cookies) so the backend can authenticate the user (JWT/session).

So: **Hook → service (getProducts / getProduct) → apiFetch → HTTP GET to FastAPI.**

### 4. Backend: API route (Python)

FastAPI receives the request and delegates to a **router**, then to a **service**.

**List:**

- File: `sorento_crm_backend/app/api/v1/master_data/products.py`
- Route: `GET /` on the products router.
- Mounted as: `/api/v1` + `/master-data` + `/products` → **GET /api/v1/master-data/products**.
- Handler: `get_products(page, limit, query, category_id, brand_id, status, sort, dir, ...)`.
  - It gets `current_user` (JWT) and `db` (database session) via **dependencies**.
  - Creates `ProductService(db)` and calls `service.list_products(page=page, limit=limit, query=query, ...)`.
  - Returns the result (FastAPI turns it into JSON using the route’s `response_model`).

**Detail:**

- Same file: `GET /{product_id}` → **GET /api/v1/master-data/products/{id}**.
- Handler: `get_product(product_id)` → `ProductService(db).get_product(product_id)` → return one product.

So: **HTTP request → FastAPI route → dependencies (auth, db) → ProductService → return dict/object → JSON response.**

### 5. Backend: Service and database (Python)

Business logic and DB access live in the **service**.

- File: `sorento_crm_backend/app/services/product_service.py`

**List:**

- `list_products(...)`:
  - Builds a SQLAlchemy query: `self.db.query(Product)`.
  - Applies filters (category, brand, status, price range, search on `product_code` / `product_name`).
  - Gets total count, applies sorting, then **offset/limit** for pagination.
  - Runs: `q.offset(offset).limit(limit).all()` → list of `Product` ORM objects.
  - Returns a dict: `{ "data": products, "pagination": { "total", "page", "limit" }, "empty": ... }`.

**Detail:**

- `get_product(product_id)`:
  - `self.db.query(Product).filter(Product.id == product_id).first()`.
  - If not found, raises HTTP 404; otherwise returns the product object.

FastAPI then serializes these return values to JSON (using Pydantic schemas like `ProductResponse`, `ListResponse[ProductResponse]`).

So: **Route → ProductService → SQLAlchemy → PostgreSQL → Python objects → JSON.**

### 6. Backend: Database

- **ORM:** SQLAlchemy.
- **Tables:** e.g. `products` (and related tables for categories, brands, etc.).
- **Connection:** Backend gets `DATABASE_URL` from env and creates a session per request via `get_db()`. The service uses that session for all queries.

So: **ProductService uses `self.db` (Session) → SQLAlchemy runs SQL on PostgreSQL.**

### 7. Frontend: Display

- **List:** React Query’s `data` holds `{ data: Product[], pagination: {...}, empty }`. The list component maps `data.data` into table rows (with sorting, filters, pagination controls).
- **Detail:** `data` is a single product; the detail component shows `product.product_name`, `product.product_code`, `product.list_price`, etc., and may use the same service for related data (e.g. attachments, stock).

So: **JSON response → React Query cache → component re-renders → UI shows products.**

---

## Flow Diagram (Product List)

```
User opens product list page
         │
         ▼
  ProductsList.tsx
  useQuery(['products', ...])  →  queryFn: fetchProducts(...)
         │
         ▼
  productService.getProducts(params)
  → apiFetch('/api/v1/master-data/products?page=1&limit=50&sort=created_at&dir=desc', { method: 'GET' })
         │
         ▼
  HTTP GET  →  FastAPI backend (e.g. http://localhost:8000/api/v1/master-data/products?...)
         │
         ▼
  products.py: get_products(...)
  → ProductService(db).list_products(page, limit, query, ...)
         │
         ▼
  product_service.py: list_products(...)
  → self.db.query(Product).filter(...).order_by(...).offset(...).limit(...).all()
         │
         ▼
  PostgreSQL  →  returns rows  →  SQLAlchemy maps to Product objects
         │
         ▼
  Service returns { data: [...], pagination: {...}, empty }
         │
         ▼
  FastAPI serializes to JSON (response_model=ListResponse[ProductResponse])
         │
         ▼
  HTTP 200 + JSON body  →  Frontend apiFetch gets response.json()
         │
         ▼
  React Query stores result  →  ProductsList renders table from data.data
```

The same idea applies to **product detail**: replace “list” with `getProduct(id)`, `get_product(product_id)`, and `get_product(product_id)` in the service; the response is one product object instead of a list.

---

## Files to Open (In Order)

If your friend wants to trace the flow in the repo:

| Step | Layer | File (frontend) | File (backend) |
|------|--------|------------------|----------------|
| 1 | Page | `sorento_crm_frontend/.../products/page.tsx`, `.../products/[id]/page.tsx` | — |
| 2 | Component + hook | `.../products/components/ProductsList.tsx`, `.../products/[id]/components/ProductDetail.tsx` | — |
| 3 | Hook / React Query | `.../products/hooks/useProducts.ts` | — |
| 4 | API call (service) | `.../products/services/productService.ts` | — |
| 5 | HTTP helper | `sorento_crm_frontend/lib/api.ts` (`apiFetch`) | — |
| 6 | Route | — | `sorento_crm_backend/app/api/v1/master_data/products.py` |
| 7 | Service + DB | — | `sorento_crm_backend/app/services/product_service.py` |
| 8 | Models / schemas | `.../products/types/product.types.ts` | `app/models/product.py`, `app/schemas/product.py` |

---

## Concepts Worth Knowing for the Test

- **Frontend (TypeScript):**  
  React components, hooks, React Query (queryKey, queryFn), async/await, typing (interfaces for API responses), `fetch` or a wrapper like `apiFetch`.

- **Backend (Python):**  
  FastAPI router and route functions, dependency injection (`Depends(get_current_user)`, `Depends(get_db)`), Pydantic request/response models, service layer, SQLAlchemy Session and queries (filter, order_by, offset, limit), returning dicts or ORM objects that FastAPI serializes to JSON.

- **End-to-end:**  
  One logical “product list” or “product detail” flow: URL path, query params or path params, who builds them (frontend), who reads them (backend), where the DB is queried (service), and how the result gets back to the UI (JSON → React state → render).

This one flow (product list + product detail) is a solid template for “how the frontend sends an API request to the backend to query the database and display the result.” Your friend can reuse the same mental model for other entities (orders, users, etc.) in the same codebase.
