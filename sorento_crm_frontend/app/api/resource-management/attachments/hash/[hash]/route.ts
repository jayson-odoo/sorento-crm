import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ hash: string }> },
) {
  const { hash } = await params;
  // Note: If FastAPI doesn't have this endpoint, it will return 404
  return proxyToFastAPI(request as NextRequest, `/api/v1/resource-management/attachments/hash/${hash}`);
}
