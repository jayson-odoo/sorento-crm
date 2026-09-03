'use client';

import { useQuery } from '@tanstack/react-query';
import {
  getSigninBranding,
  NO_SIGNIN_BRANDING,
  type SigninBranding,
} from '../services/brandingService';

export const signinBrandingKey = ['signin-branding'];

/**
 * The admin-uploaded sign-in background, if there is one.
 *
 * `enabled` is the caller's, because only the credential pages wear the backdrop - the contact
 * portal and the counter-sign page own their whole viewport and must not pay for a request they
 * will not use.
 *
 * No retries and no error surface: the service already resolves every failure to "no background",
 * so the page falls back to the designed default without the visitor ever learning that a request
 * happened. This is what lets the frontend ship ahead of the backend route.
 */
export function useSigninBranding(enabled: boolean): SigninBranding {
  const { data } = useQuery({
    queryKey: signinBrandingKey,
    queryFn: getSigninBranding,
    enabled,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  return data ?? NO_SIGNIN_BRANDING;
}
