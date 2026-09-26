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
 * =========================================================================
 * EXPECTED API CONTRACT (Phase 1 - locked for Phase 2 backend work)
 * See documentation/plans/identity/s1-contract.md
 * =========================================================================
 *
 * POST /api/v1/auth/phone/request-code
 *   Body: { phone: string }  (any format; normalised server-side)
 *   200: { sent_to: string, expires_in_seconds: number, resend_in_seconds: number }
 *     - same body whether or not the number belongs to anyone (no enumeration)
 *   422: detail "Enter a valid phone number."
 *   429: detail = { code: "RATE_LIMITED", message, retry_after_seconds }
 * =========================================================================
 */

import { extractApiError } from '@/lib/api-client';

// Phase 1 mock, swapped in Phase 2: flip this to false once the backend
// route above exists and remove `requestSigninCodeMock`.
const USE_MOCK = true;

export interface RequestSigninCodeResult {
  sent_to: string;
  expires_in_seconds: number;
  resend_in_seconds: number;
}

const MOCK_DELAY_MS = 400;
const MOCK_EXPIRES_IN_SECONDS = 600;
const MOCK_RESEND_IN_SECONDS = 60;

/** `+60••••<last 4 digits>` of the TYPED number, mirroring the backend's mask. */
function maskPhone(typed: string): string {
  const digits = typed.replace(/\D/g, '');
  const last4 = digits.slice(-4);
  return `+60••••${last4}`;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function requestSigninCodeMock(phone: string): Promise<RequestSigninCodeResult> {
  await delay(MOCK_DELAY_MS);
  const digits = phone.replace(/\D/g, '');
  if (digits.includes('999')) {
    throw new Error('Too many tries. Try again in 12 minutes.');
  }
  if (digits.length < 8) {
    throw new Error('Enter a valid phone number.');
  }
  return {
    sent_to: maskPhone(phone),
    expires_in_seconds: MOCK_EXPIRES_IN_SECONDS,
    resend_in_seconds: MOCK_RESEND_IN_SECONDS,
  };
}

function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  return configured ? configured.replace(/\/$/, '') : '';
}

async function requestSigninCodeReal(phone: string): Promise<RequestSigninCodeResult> {
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

export async function requestSigninCode(phone: string): Promise<RequestSigninCodeResult> {
  return USE_MOCK ? requestSigninCodeMock(phone) : requestSigninCodeReal(phone);
}

const MOCK_VERIFY_ERRORS: Record<string, string> = {
  '000000': 'That code is not right. 4 tries left.',
  '111111': 'That code has expired. Send a new one.',
};

/**
 * Phase 1 mock only: lets the verify step's error states be tuned before the
 * backend's `/api/v1/auth/phone/verify` exists, without having to fake a
 * NextAuth response. Returns null (real `signIn('phone-otp', ...)` call goes
 * through, and errors until Phase 2 lands - that is fine) once `USE_MOCK`
 * flips to false.
 */
export function mockVerifyError(code: string): string | null {
  if (!USE_MOCK) return null;
  return MOCK_VERIFY_ERRORS[code] ?? null;
}
