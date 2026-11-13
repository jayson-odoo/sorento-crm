import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import DispatchBoard from '../service-jobs/components/DispatchBoard';

export const metadata: Metadata = {
  title: 'Dispatch Board',
};

export default function DispatchBoardPage() {
  return (
    <>
      <Container>
        <PageHeader title="Dispatch Board" />
      </Container>
      <Container>
        <DispatchBoard />
      </Container>
    </>
  );
}
