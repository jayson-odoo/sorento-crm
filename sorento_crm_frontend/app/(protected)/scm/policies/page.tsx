import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PolicyConfigView } from './components/PolicyConfigView';

export const metadata: Metadata = {
  title: 'Supply Chain Policies',
  description: 'Tune reorder policies, classification thresholds and supplier scoring.',
};

export default function ScmPoliciesPage() {
  return (
    <RequireAccess permission="scm.policy.manage">
      <Container width="fluid">
        <PageHeader title="Policies" />
      </Container>

      <Container width="fluid">
        <PolicyConfigView />
      </Container>
    </RequireAccess>
  );
}
