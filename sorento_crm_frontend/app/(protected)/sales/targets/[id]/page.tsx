import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import TargetPageHeader from '../components/TargetPageHeader';
import TargetRecord from '../components/TargetRecord';

export const metadata: Metadata = {
  title: 'Target',
  description: 'A sales target, its periods and what it has achieved.',
};

export default async function TargetPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <Container>
        <TargetPageHeader id={id} />
      </Container>
      <Container>
        <TargetRecord id={id} />
      </Container>
    </>
  );
}
