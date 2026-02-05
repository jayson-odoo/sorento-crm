import { NextRequest, NextResponse } from 'next/server';

export function requireExternalApiKey(request: NextRequest): NextResponse | null {
  const apiKey = request.headers.get('X-API-Key');
  const expectedKey = process.env.EXTERNAL_API_KEY;

  if (!expectedKey) {
    return NextResponse.json({ message: 'EXTERNAL_API_KEY not configured' }, { status: 500 });
  }

  if (!apiKey || apiKey !== expectedKey) {
    return NextResponse.json({ message: 'Invalid API key' }, { status: 401 });
  }

  return null;
}
