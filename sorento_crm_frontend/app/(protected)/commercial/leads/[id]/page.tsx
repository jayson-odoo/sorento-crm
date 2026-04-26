import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import LeadDetail from '../components/LeadDetail';

export const metadata: Metadata = {
  title: 'Lead',
  description: 'Lead detail.',
};

export default async function CommercialLeadDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Container>
      <LeadDetail leadId={id} />
    </Container>
  );
}
