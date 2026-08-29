'use client';

import dynamic from 'next/dynamic';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';

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
      {/* The only page in the app that never said what it was: every other route
          opens with a title, and the landing page opened with a widget. */}
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>Dashboard</ToolbarTitle>
        </ToolbarHeading>
        <ToolbarActions />
      </Toolbar>
      {/* MyPendingSLAWidget carries the My Pending / My Team / Coverage tabs so the
          dashboard stays a single compact surface. */}
      <div className="mb-5">
        <MyPendingSLAWidget />
      </div>
      {/* Home embed: bound the (expensive, full-table) KPI aggregates to the last
          30 days. The dedicated /sla-management/kpi-dashboard route stays all-time. */}
      <SLAKpiDashboardContent defaultWindowDays={30} />
    </Container>
  );
}
