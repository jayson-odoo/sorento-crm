# Quick Fix for 404 OPTIONS Error

## Issue
Getting `404 Not Found` on OPTIONS preflight request to `/api/v1/order-management/orders`

## Solution

The route is correctly registered. The issue is likely one of:

1. **FastAPI server needs restart** - After route changes, restart the server
2. **CORS configuration** - Ensure CORS origins include your frontend URL
3. **Route path** - The route should be accessible at `/api/v1/order-management/orders/` (with trailing slash)

## Steps to Fix

1. **Restart FastAPI server:**
   ```bash
   cd sorento_crm_backend
   # Stop current server (Ctrl+C)
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Verify CORS origins in `.env`:**
   ```env
   CORS_ORIGINS=http://localhost:3000,http://localhost:3001
   ```

3. **Test the route directly:**
   ```bash
   curl -X GET http://localhost:8000/api/v1/order-management/orders
   ```

4. **Check if route is registered:**
   Visit http://localhost:8000/docs and look for the order-management routes

## Route Structure

The route is registered as:
- Base: `/api/v1` (from `app.include_router(api_router, prefix="/api/v1")`)
- Module: `/order-management` (from `api_router.include_router(order_management.router, prefix="/order-management")`)
- Resource: `/orders` (from `order_management.router.include_router(orders.router, prefix="/orders")`)
- Endpoint: `/` (from `@router.get("/")`)

**Full path:** `/api/v1/order-management/orders/`

FastAPI should handle both `/orders` and `/orders/` automatically.
