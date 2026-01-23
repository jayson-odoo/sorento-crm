'use client';

import dynamic from 'next/dynamic';
import { Container } from '@/components/common/container';

// Dynamically import SLATrackingDashboard with SSR disabled to avoid window is not defined errors
const SLATrackingDashboard = dynamic(
  () => import('./sla-management/conversation-sla-tracking/components/SLATrackingDashboard'),
  { ssr: false }
);

export default function Page() {
  return (
    <Container>
      <SLATrackingDashboard />
    </Container>
  );
}
