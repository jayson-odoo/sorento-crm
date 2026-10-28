import { Suspense } from 'react';
import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import OwnPriceTagRequest from '../components/OwnPriceTagRequest';

export const metadata: Metadata = {
  title: 'New Price Tag Request',
  description: 'Raise a price tag request',
};

/** A salesperson's new request: the request page in create mode (PORTAL-P4-REQUESTS S7). */
export default function NewPriceTagRequestPage() {
  return (
    <Container>
      <Suspense fallback={null}>
        <OwnPriceTagRequest />
      </Suspense>
    </Container>
  );
}
