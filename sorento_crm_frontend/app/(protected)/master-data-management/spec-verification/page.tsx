import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SpecVerificationList from './components/SpecVerificationList';

export const metadata: Metadata = {
  title: 'Spec Verification',
  description: 'Review and verify product specifications.',
};

export default async function SpecVerificationPage() {
  return (
    <>
      <Container>
        <PageHeader title="Spec Verification" />
      </Container>

      <Container>
        <SpecVerificationList />
      </Container>
    </>
  );
}
