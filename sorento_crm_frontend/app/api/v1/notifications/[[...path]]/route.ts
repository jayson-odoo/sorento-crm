import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

async function handleProxy(
  request: NextRequest,
  params: Promise<{ path?: string[] }>,
  method?: string,
) {
  const { path = [] } = await params;
  const segment = path.length ? `/${path.join('/')}` : '';
  const targetPath = `/api/v1/notifications${segment}`;
  // Only read body for methods that typically have one (POST); PATCH with no body must not consume stream
  const isBodyMethod = method && !['GET', 'HEAD'].includes(method);
  const body =
    isBodyMethod && method === 'POST'
      ? await request.json().catch(() => undefined)
      : undefined;

  return proxyToFastAPI(request, targetPath, {
    method: method || request.method,
    body,
  });
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path?: string[] }> },
) {
  return handleProxy(request, params, 'GET');
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path?: string[] }> },
) {
  return handleProxy(request, params, 'POST');
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path?: string[] }> },
) {
  return handleProxy(request, params, 'PATCH');
}
