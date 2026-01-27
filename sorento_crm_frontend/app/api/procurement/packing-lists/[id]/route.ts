import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  return proxyToFastAPI(request as NextRequest, `/api/v1/procurement/packing-lists/${id}`);
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const body = await request.json();
  return proxyToFastAPI(request, `/api/v1/procurement/packing-lists/${id}`, {
    method: 'PUT',
    body,
  });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  return proxyToFastAPI(request, `/api/v1/procurement/packing-lists/${id}`, {
    method: 'DELETE',
  });
}
