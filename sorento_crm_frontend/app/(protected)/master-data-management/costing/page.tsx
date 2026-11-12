import { Suspense } from 'react';
import { Metadata } from 'next';
import CostingView from './components/CostingView';

export const metadata: Metadata = {
  title: 'Costing',
  description: 'Landing cost, mark-ups and party prices for every product.',
};

export default function CostingPage() {
  // The view reads the party, filters and as-of date off the URL (useSearchParams).
  return (
    <Suspense>
      <CostingView />
    </Suspense>
  );
}
