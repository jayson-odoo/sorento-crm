import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import CompaniesList from './components/CompaniesList';

export const metadata: Metadata = {
  title: 'Companies',
  description: 'Manage companies.',
};

export default async function CompaniesPage() {
  return (
    <RequireAccess superadmin>
      <Container>
        <PageHeader title="Companies" />
      </Container>

      <Container>
        <CompaniesList />
      </Container>
    </RequireAccess>
  );
}
