/**
 * Account > Security - set/change the signed-in user's password
 * (PLAN-unified-identity-26sep.md S1, plan 5.3).
 *
 * Authenticated call: `apiFetch` (attaches the NextAuth bearer), matching
 * every other `/api/v1/*` call in the app - not the account page's Next.js
 * BFF prefix (`/api/user-management/account/*`), which is a different,
 * older proxy for the profile/logs routes only.
 *
 * =========================================================================
 * EXPECTED API CONTRACT (Phase 1 - locked for Phase 2 backend work)
 * See documentation/plans/identity/s1-contract.md
 * =========================================================================
 *
 * POST /api/v1/auth/password
 *   Body: { current_password?: string, new_password: string }
 *   - current_password required + checked when the user already has one
 *     (400 "Current password is not right.")
 *   - new_password: 8+ characters
 *   200: on success every OTHER session of the user is revoked.
 * =========================================================================
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

// Phase 1 mock, swapped in Phase 2: flip this to false once the backend
// route above exists and remove `setPasswordMock`.
const USE_MOCK = true;

export interface SetPasswordInput {
  current_password?: string;
  new_password: string;
}

const MOCK_DELAY_MS = 400;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function setPasswordMock(input: SetPasswordInput): Promise<void> {
  await delay(MOCK_DELAY_MS);
  if (input.current_password === 'wrong') {
    throw new Error('Current password is not right.');
  }
}

async function setPasswordReal(input: SetPasswordInput): Promise<void> {
  const response = await apiFetch('/api/v1/auth/password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save password.'));
  }
}

export async function setPassword(input: SetPasswordInput): Promise<void> {
  return USE_MOCK ? setPasswordMock(input) : setPasswordReal(input);
}
