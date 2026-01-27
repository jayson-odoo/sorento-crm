import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

async function handleProxy(
  request: NextRequest,
  params: Promise<{ path?: string[] }>,
  method?: string,
) {
  const { path = [] } = await params;
  // Backend integration routes are mounted under /api/v1/integrations/logs
  // Map /integration-management/integration-logs/* -> /integrations/logs/*
  const [firstSegment, ...rest] = path;
  const targetPath =
    firstSegment === 'integration-logs'
      ? `/api/v1/integrations/logs/${rest.join('/')}`
      : `/api/v1/integration-management/${path.join('/')}`;
  const isBodyMethod = method && !['GET', 'HEAD'].includes(method);
  const body = isBodyMethod ? await request.json().catch(() => undefined) : undefined;

  return proxyToFastAPI(request, targetPath, {
    method,
    body,
    requireAuth: false,
  });
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  return handleProxy(request, params, 'GET');
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  return handleProxy(request, params, 'POST');
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  return handleProxy(request, params, 'PUT');
}

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  return handleProxy(request, params, 'PATCH');
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  return handleProxy(request, params, 'DELETE');
}
