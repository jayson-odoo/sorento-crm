import { Suspense } from 'react';
import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { RoomDesigner } from './components/RoomDesigner';

export const metadata: Metadata = {
  title: 'Room Designer',
  description: 'Shape a room and place products in it at their real size.',
};

export default function DealerKitDesignPage() {
  return (
    <Container width="fluid">
      <PageHeader title="Room Designer" />

      {/* RoomDesigner reads ?from=, so it needs a boundary: useSearchParams
          forces client rendering and `next build` fails on a statically
          rendered page without one. */}
      <Suspense fallback={null}>
        <RoomDesigner />
      </Suspense>
    </Container>
  );
}
