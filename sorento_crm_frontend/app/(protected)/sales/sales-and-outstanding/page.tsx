import { Suspense } from 'react';
import { Metadata } from 'next';
import { SalesAndOutstandingView } from './SalesAndOutstandingView';

export const metadata: Metadata = {
  title: 'Sales & outstanding',
  description: 'Sales & outstanding',
};

export default function SalesAndOutstandingPage() {
  return (
    <Suspense fallback={null}>
      <SalesAndOutstandingView />
    </Suspense>
  );
}
