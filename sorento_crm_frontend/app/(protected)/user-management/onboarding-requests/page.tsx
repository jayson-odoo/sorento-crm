import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { OnboardingRequestList } from './components/OnboardingRequestList';

export const metadata: Metadata = {
  title: 'Onboarding Requests',
  description: 'Review submitted people and provision their access.',
};

export default function OnboardingRequestsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Onboarding Requests" />
      </Container>
      <Container>
        <OnboardingRequestList />
      </Container>
    </>
  );
}
