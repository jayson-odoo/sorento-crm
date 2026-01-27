import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

export async function POST(request: NextRequest) {
  const body = await request.json();
  // Note: FastAPI verify-email endpoint can be used for token verification
  // Or create a dedicated /verify-token endpoint
  return proxyToFastAPI(request, '/api/v1/auth/verify-email', {
    method: 'POST',
    body: { token: body.token },
  });
}
