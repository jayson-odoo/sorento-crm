import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PartyDetailClient } from './components/PartyDetailClient';

export const metadata: Metadata = {
  title: 'Party',
  description: 'One organisation, how to reach them, and how much work they bring us.',
};

export default async function ProjectPartyDetailPage({
  params,
}: {
  params: Promise<{ partyId: string }>;
}) {
  const { partyId } = await params;
  return (
    <RequireAccess permission="projects.parties.view">
      <Container className="space-y-6">
        <PageHeader title="Party" />
        <PartyDetailClient partyId={partyId} />
      </Container>
    </RequireAccess>
  );
}
