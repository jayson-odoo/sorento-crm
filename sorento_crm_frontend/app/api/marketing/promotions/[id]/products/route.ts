import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  // Note: If FastAPI doesn't have this endpoint, it will return 404
  // Should be at /api/v1/marketing/promotions/{id}/products
  return proxyToFastAPI(request as NextRequest, `/api/v1/marketing/promotions/${id}/products`);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const body = await request.json();
  // Note: If FastAPI doesn't have this endpoint, it will return 404
  return proxyToFastAPI(request, `/api/v1/marketing/promotions/${id}/products`, {
    method: 'POST',
    body,
  });
}
