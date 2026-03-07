import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

const CAMEL_TO_SNAKE: Record<string, string> = {
  websiteURL: 'website_url',
  supportEmail: 'support_email',
  supportPhone: 'support_phone',
  currencyFormat: 'currency_format',
  logoFile: 'logo_file',
  logoAction: 'logo_action',
};

function toSnakeCaseKey(key: string): string {
  return CAMEL_TO_SNAKE[key] ?? key.replace(/([A-Z])/g, '_$1').toLowerCase().replace(/^_/, '');
}

function coerceValue(value: unknown): unknown {
  if (value === '' || value === undefined) return undefined;
  if (typeof value === 'string') {
    if (value === 'true') return true;
    if (value === 'false') return false;
  }
  return value;
}

export async function POST(request: NextRequest) {
  const formData = await request.formData();
  const body: Record<string, unknown> = {};

  formData.forEach((value, key) => {
    if (key === 'logoFile') return;
    const snakeKey = toSnakeCaseKey(key);
    const raw = value instanceof File ? value.name : value;
    body[snakeKey] = coerceValue(raw);
  });

  return proxyToFastAPI(request, '/api/v1/user-management/settings/general', {
    method: 'PUT',
    body,
  });
}
