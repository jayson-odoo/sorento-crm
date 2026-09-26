import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { SalesTargetPage } from './components/SalesTargetPage';

export const metadata: Metadata = {
  title: 'Target',
  description: 'A sales target, its periods and what it has achieved.',
};

export default async function TargetPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <Container>
        <PageHeader
          title="Target"
          actions={<BackToList listPath="/sales/targets" label="Back to targets" />}
        />
      </Container>
      <Container>
        <SalesTargetPage id={id} />
      </Container>
    </>
  );
}
