import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import FormSLATrackingList from './components/FormSLATrackingList';

export const metadata: Metadata = {
  title: 'Form SLA Tracking',
  description: 'View form SLA tracking and responsiveness metrics across entities.',
};

export default async function FormSLATrackingPage() {
  return (
    <>
      <Container>
        <PageHeader title="Form SLA Tracking" />
      </Container>

      <Container>
        <FormSLATrackingList />
      </Container>
    </>
  );
}
