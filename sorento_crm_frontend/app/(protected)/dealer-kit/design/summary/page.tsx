import { Suspense } from 'react';
import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { DesignSummary } from './components/DesignSummary';

export const metadata: Metadata = {
  title: 'Design Summary',
  description: 'What the design comes to, and what is on the quote.',
};

export default function DealerKitSummaryPage() {
  return (
    <Container width="fluid">
      <PageHeader title="Design Summary" />

      {/* Reads ?selection=, so it needs a boundary or `next build` refuses to
          prerender the page. */}
      <Suspense fallback={null}>
        <DesignSummary />
      </Suspense>
    </Container>
  );
}
