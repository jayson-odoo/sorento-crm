import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import TrackingValidationList from './components/TrackingValidationList';

export const metadata: Metadata = {
  title: 'Tracking Validation',
  description:
    'Compare liner and CIDB feed observations against the dates entered by hand.',
};

export default function TrackingValidationPage() {
  return (
    <RequireAccess superadmin>
      <Container>
        <PageHeader title="Tracking Validation" />
      </Container>

      <Container>
        <TrackingValidationList />
      </Container>
    </RequireAccess>
  );
}
