import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function DELETE(request: NextRequest) {
  const body = await request.json();
  const { permissionIds } = body;
  
  return proxyToFastAPI(request, '/api/v1/user-management/permissions/bulk', {
    method: 'DELETE',
    body: permissionIds,
  });
}
