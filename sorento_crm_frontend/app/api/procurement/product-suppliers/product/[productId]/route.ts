import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ productId: string }> },
) {
  const { productId } = await params;
  return proxyToFastAPI(request as NextRequest, `/api/v1/procurement/product-suppliers/product/${productId}`);
}
