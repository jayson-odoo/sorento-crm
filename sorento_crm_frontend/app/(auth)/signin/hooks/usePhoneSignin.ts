'use client';

/**
 * `/signin`'s Phone tab, step 1: request a WhatsApp OTP.
 *
 * Layering: UI -> this hook -> `services/phoneSigninService.ts` -> `lib/api-client`
 * -> backend (PLAN-unified-identity-26sep.md S1). Step 2 (submitting the code)
 * goes through NextAuth's `phone-otp` provider directly from the page, the
 * same way the Email tab calls `signIn('credentials', ...)` - there is no
 * mutation hook for it, since NextAuth's own `signIn()` already is the call.
 */

import { useMutation } from '@tanstack/react-query';
import {
  requestSigninCode,
  type RequestSigninCodeResult,
} from '@/services/phoneSigninService';

export function useRequestSigninCode() {
  return useMutation<RequestSigninCodeResult, Error, string>({
    mutationFn: (phone: string) => requestSigninCode(phone),
  });
}
