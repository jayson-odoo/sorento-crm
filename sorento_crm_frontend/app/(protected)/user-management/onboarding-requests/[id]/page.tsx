'use client';

import { use } from 'react';
import { OnboardingRequestDetail } from './components/OnboardingRequestDetail';

/**
 * The review screen owns its own Toolbar: the pager, the status-gated primary
 * action and the gear menu all read the request, so splitting the shell off
 * here would only mean fetching it twice.
 */
export default function OnboardingRequestDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <OnboardingRequestDetail requestId={id} />;
}
