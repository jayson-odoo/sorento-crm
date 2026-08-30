import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { PageEditorScreen } from './components/PageEditorScreen';

export const metadata: Metadata = {
  title: 'Page Builder',
  description: 'Lay out a catalogue page across desktop, tablet, mobile and paper.',
};

export default async function DealerKitPageEditorRoute({
  params,
}: {
  params: Promise<{ pageId: string }>;
}) {
  const { pageId } = await params;

  return (
    <Container width="fluid">
      <PageHeader title="Page Builder" />

      <PageEditorScreen pageId={pageId} />
    </Container>
  );
}
