'use client';

import dynamic from 'next/dynamic';

// Dynamically import SLATrackingDashboard with SSR disabled to avoid window is not defined errors
const SLATrackingDashboard = dynamic(() => import('./SLATrackingDashboard'), { ssr: false });

export default function SLATrackingDashboardWrapper() {
  return <SLATrackingDashboard />;
}
