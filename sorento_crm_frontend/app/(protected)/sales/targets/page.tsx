import { Suspense } from 'react';
import { Metadata } from 'next';
import SalesTargetsView from './components/SalesTargetsView';

export const metadata: Metadata = {
  title: 'Targets',
  description: 'Sales targets for teams and agents, with live achievement.',
};

export default function SalesTargetsPage() {
  // The view reads its tab, date and team filter off the URL (useSearchParams).
  return (
    <Suspense>
      <SalesTargetsView />
    </Suspense>
  );
}
