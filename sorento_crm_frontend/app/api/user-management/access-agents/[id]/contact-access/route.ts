import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  return proxyToFastAPI(request as NextRequest, `/api/v1/user-management/access-agents/${id}/contact-access`);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const body = await request.json();
  return proxyToFastAPI(request, `/api/v1/user-management/access-agents/${id}/contact-access`, {
    method: 'POST',
    body,
  });
}
