'use client';

import dynamic from 'next/dynamic';
import { Container } from '@/components/common/container';

const MyPendingSLAWidget = dynamic(
  () => import('./sla-management/conversation-sla-tracking/components/MyPendingSLAWidget'),
  { ssr: false }
);

// Home dashboard now embeds the full SLA KPI dashboard (the one under the SLA
// Management menu) directly under "My pending tasks". The older SLATrackingDashboard
// was removed per product direction.
const SLAKpiDashboardContent = dynamic(
  () =>
    import('./sla-management/kpi-dashboard/SLAKpiDashboardContent').then(
      (m) => m.SLAKpiDashboardContent,
    ),
  { ssr: false }
);

export default function Page() {
  return (
    // Fluid so the dashboard fills the screen width instead of capping at 1320px.
    <Container width="fluid">
      <div className="mb-5">
        <MyPendingSLAWidget />
      </div>
      <SLAKpiDashboardContent />
    </Container>
  );
}
