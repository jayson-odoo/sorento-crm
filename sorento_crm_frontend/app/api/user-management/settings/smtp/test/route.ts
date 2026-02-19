import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function POST(request: NextRequest) {
  return proxyToFastAPI(request, '/api/v1/user-management/settings/smtp/test', {
    method: 'POST',
  });
}
