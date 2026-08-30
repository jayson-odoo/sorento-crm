import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { EditionDetail } from './components/EditionDetail';

export const metadata: Metadata = {
  title: 'Edition',
  description: 'Approve, reject or publish a catalogue revision.',
};

export default async function DealerKitEditionPage({
  params,
}: {
  params: Promise<{ editionId: string }>;
}) {
  const { editionId } = await params;

  return (
    <Container width="fluid">
      <PageHeader title="Edition" />

      <EditionDetail editionId={editionId} />
    </Container>
  );
}
