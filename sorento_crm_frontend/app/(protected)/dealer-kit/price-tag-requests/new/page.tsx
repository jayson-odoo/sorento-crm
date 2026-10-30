import { Suspense } from 'react';
import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PortalPriceTagRequest } from '../components/PriceTagRequestPage';

export const metadata: Metadata = {
  title: 'New Price Tag Request',
  description: 'Raise a price tag request',
};

/** A salesperson's new request: the portal's own form in create mode (PORTAL-P4-REQUESTS R3). */
export default function NewPriceTagRequestPage() {
  return (
    <Container>
      <Suspense fallback={null}>
        <PortalPriceTagRequest />
      </Suspense>
    </Container>
  );
}
