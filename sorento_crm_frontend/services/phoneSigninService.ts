/**
 * Phone sign-in - request a WhatsApp OTP for `/signin`'s Phone tab
 * (PLAN-unified-identity-26sep.md S1, AC-20 to AC-23).
 *
 * Public, unauthenticated route - same shape as the sign-in page's other
 * unauthenticated calls (`app/(auth)/services/brandingService.ts`): plain
 * `fetch` (never `apiFetch`, which mints a NextAuth bearer nobody has yet)
 * against a resolved base, since the dev rewrite only proxies `/api/v1/*`
 * when `NEXT_PUBLIC_API_URL` is unset.
 *
 * POST /api/v1/auth/phone/request-code
 *   Body: { phone: string }  (any format; normalised server-side)
 *   200: { sent_to: string, expires_in_seconds: number, resend_in_seconds: number }
 *     - same body whether or not the number belongs to anyone (no enumeration)
 *   422: detail "Enter a valid phone number."
 *   429: detail = { code: "RATE_LIMITED", message, retry_after_seconds }
 *
 * See documentation/plans/identity/s1-contract.md.
 */

import { extractApiError } from '@/lib/api-client';

export interface RequestSigninCodeResult {
  sent_to: string;
  expires_in_seconds: number;
  resend_in_seconds: number;
}

function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  return configured ? configured.replace(/\/$/, '') : '';
}

export async function requestSigninCode(phone: string): Promise<RequestSigninCodeResult> {
  const response = await fetch(`${apiBase()}/api/v1/auth/phone/request-code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to send verification code.'));
  }
  return (await response.json()) as RequestSigninCodeResult;
}
