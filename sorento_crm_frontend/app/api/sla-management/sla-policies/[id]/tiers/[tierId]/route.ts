import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; tierId: string }> },
) {
  const { id, tierId } = await params;
  const body = await request.json();
  return proxyToFastAPI(request, `/api/v1/sla-management/sla-policies/${id}/tiers/${tierId}`, {
    method: 'PUT',
    body,
  });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; tierId: string }> },
) {
  const { id, tierId } = await params;
  return proxyToFastAPI(request, `/api/v1/sla-management/sla-policies/${id}/tiers/${tierId}`, {
    method: 'DELETE',
  });
}
