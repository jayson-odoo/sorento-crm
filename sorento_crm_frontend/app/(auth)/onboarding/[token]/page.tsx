'use client';

/**
 * The intake link: `/onboarding/{token}`.
 *
 * In the `(auth)` group and therefore NextAuth-independent - the requester has
 * no CRM account and will never get one. The token is in the PATH rather than a
 * query string so the URL survives being pasted into WhatsApp, bookmarked and
 * re-opened, which is exactly the "edits over several days" reality the
 * multi-use token exists for (UAC AC-3.2).
 */

import { use } from 'react';
import { IntakeScreen } from '../components/IntakeScreen';

export default function OnboardingIntakePage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);
  return <IntakeScreen token={token} />;
}
